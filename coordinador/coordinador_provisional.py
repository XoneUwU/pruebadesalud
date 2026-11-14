"""Coordinador PROVISIONAL de «¿Está apto hoy?», hasta que esté el coordinador de Danilo.

Junta los datos de una sesión de la estación y publica el semáforo con reglas simples y visibles:

  lee      apto/control/sesion            {"persona", "tarea", "sesion"}
  lee      apto/{persona}/pvt, dsst, cuestionario, voz, vision
  publica  apto/{persona}/evaluacion      (retain) color, puntaje, motivos, accion, senales, provisional: true
  publica  apto/{persona}/semaforo        (retain) color, provisional: true

Calcula cuando llega el cuestionario (el último paso de la estación) y vuelve a calcular si después
llega otro dato de la misma sesión (por ejemplo, la visión). Las mediciones marcadas con linea_base
se guardan en datos/coordinador/linea_base.jsonl y sirven para comparar las siguientes.

  python coordinador/coordinador_provisional.py

REGLAS (cada señal da 0, 1 o 2 puntos; con línea base se compara con el promedio de la persona,
sin línea base con valores fijos de referencia del prototipo, que hay que calibrar):
  PVT           reacción media: +10 % = 1, +25 % = 2     | sin base: 350 ms = 1, 450 ms = 2
                lapsos por minuto: +1 = 1, +2 = 2         | sin base: 1 = 1, 3 = 2 (desde 2 lapsos: uno suelto no marca)
                anticipadas por minuto: 2 o más = 1
  Símbolos      aciertos por minuto: -10 % = 1, -20 % = 2 | sin base: menos de 25 = 1, menos de 15 = 2
                errores: 3 más que la base = 1            | sin base: 5 o más = 1
  Cuestionario  Karolinska: 7 = 1, 8 o 9 = 2 (escala absoluta, sin base)
                horas de sueño: 1,5 h menos = 1, 3 h menos = 2 | sin base: menos de 6 = 1, menos de 4 = 2
  Voz           "más cansada que su línea base" (de voz_fatiga.py) = 1 (señal débil: nunca 2)
  Visión        PERCLOS (0 a 1): +0,05 = 1, +0,10 = 2     | sin base: 0,15 = 1, 0,25 = 2
                parpadeos por minuto: +50 % = 1 (solo con base: lo normal varía mucho entre personas; nunca 2)
                pulso por cámara (pulso_rppg_lpm), SOLO si calidad_rppg >= CALIDAD_RPPG_MIN (0 a 1):
                +15 % = 1, +30 % = 2                       | sin base: 100 lpm = 1, 120 lpm = 2
                bostezos (desde 2 en la medición, también los tapados con la mano): 2 por minuto = 1 |
                con base: 2 por minuto más = 1 (nunca 2)
                si cara_detectada_pct < CARA_MIN_PCT (50), la visión no cuenta
                con "lentes": true (se midió con lentes puestos) los ojos (PERCLOS y parpadeos) no cuentan
  ESP32         solo lecturas con dedo y calidad >= 0,5; se usa la mediana de las de la sesión.
                pulso: +15 % = 1, +30 % = 2 | sin base: 100 = 1, 120 = 2.
                HRV (RMSSD): 25 % más baja que la base = 1, 50 % = 2 (solo con base).
                SI HAY PULSO DEL SENSOR, MANDA: el de la cámara no se usa.
                SpO2: NO suma al semáforo. Si durante al menos 30 s seguidos (lecturas con dedo y calidad >= 0,5)
                el SpO2 está 4 puntos o más por debajo del promedio de la línea base (o por debajo de 92 sin
                línea base), la evaluación lleva "aviso_spo2": true y el motivo MOTIVO_SPO2, sin cambiar el color.
Los puntos de cada fuente (pvt, dsst, cuestionario, voz, vision) son los de su peor indicador.
  rojo      si alguna fuente tiene 2 puntos, o si 3 fuentes o más tienen puntos
  amarillo  si alguna fuente tiene puntos
  verde     si ninguna
  puntaje   1 - puntos / (2 x fuentes evaluadas), solo para ordenar a quienes tienen el mismo color.
Es una sugerencia para apoyar la decisión, no un diagnóstico.
"""
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/

from comun import config  # noqa: E402
from comun.mqtt_cliente import ClienteMQTT, persona_de_tema, tema  # noqa: E402

TIPOS = ("pvt", "dsst", "cuestionario", "voz", "vision", "esp32")
ARCHIVO_BASE = config.RAIZ / "datos" / "coordinador" / "linea_base.jsonl"
ESPERA_S = 1.5  # tras el cuestionario, para juntar los mensajes que todavía vienen en camino
CALIDAD_RPPG_MIN = 0.5  # calidad_rppg (0 a 1) desde la que se cree el pulso medido por la cámara
CARA_MIN_PCT = 50       # con la cara visible menos tiempo, la visión no cuenta
CALIDAD_ESP32_MIN = 0.5  # lecturas del ESP32 con menos calidad (o sin dedo) no cuentan
# Aviso de SpO2 (no suma al semáforo)
SPO2_SEGUNDOS = 30          # tiempo seguido con el SpO2 bajo para avisar
SPO2_PUNTOS_BAJO = 4        # puntos por debajo del promedio de la línea base
SPO2_MINIMO_SIN_BASE = 92   # sin línea base: avisar por debajo de esto
MOTIVO_SPO2 = "Oxígeno más bajo de lo habitual: repetir la medición"
ACCIONES = {
    "verde": "Puede realizar la tarea",
    "amarillo": "Reasignar la tarea o hacerla en pareja, y descansar antes",
    "rojo": "No realizar la tarea crítica; reasignarla e informar al comandante",
}


# ---------------------------------------------------------------- reglas
def _num(valor) -> float | None:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return v


def _promedio(valores) -> float | None:
    vs = [v for v in valores if v is not None]
    return sum(vs) / len(vs) if vs else None


def por_minuto(m: dict, campo: str) -> float | None:
    """lapsos_por_min, o lapsos / minutos si el mensaje es viejo y no lo trae."""
    directo = _num(m.get(f"{campo}_por_min"))
    if directo is not None:
        return directo
    total, segundos = _num(m.get(campo)), _num(m.get("duracion_s"))
    return total / (segundos / 60) if total is not None and segundos else None


def _escala(valor, uno, dos) -> int:
    """0, 1 o 2 puntos según dos umbrales (mayor o igual)."""
    if valor is None:
        return 0
    return 2 if valor >= dos else 1 if valor >= uno else 0


def _indicadores(tipo: str, m: dict, base: list[dict], hay_pulso_sensor: bool = False) -> list[tuple[int, str]]:
    """(puntos, motivo) de cada indicador de una fuente."""
    r = []
    if tipo == "esp32":
        hr, hr_b = _num(m.get("pulso_lpm")), _promedio(_num(b.get("pulso_lpm")) for b in base)
        if hr is not None and hr_b:
            r.append((_escala(hr / hr_b - 1, 0.15, 0.30), "Pulso en reposo más alto de lo habitual"))
        elif hr is not None:
            r.append((_escala(hr, 100, 120), "Pulso en reposo alto"))
        hrv, hrv_b = _num(m.get("hrv_rmssd_ms")), _promedio(_num(b.get("hrv_rmssd_ms")) for b in base)
        if hrv is not None and hrv_b:  # solo contra la línea base: la HRV de 30 s varía mucho entre personas
            r.append((_escala(1 - hrv / hrv_b, 0.25, 0.50), "Variabilidad del pulso más baja de lo habitual"))
        elif hrv is not None:
            r.append((0, ""))
        return r
    if tipo == "pvt":
        rt, rt_b = _num(m.get("rt_media_ms")), _promedio(_num(b.get("rt_media_ms")) for b in base)
        if rt is not None and rt_b:
            r.append((_escala(rt / rt_b - 1, 0.10, 0.25), "Reacción más lenta de lo habitual en la prueba PVT"))
        else:
            r.append((_escala(rt, 350, 450), "Reacción lenta en la prueba PVT"))
        lpm, lpm_b = por_minuto(m, "lapsos"), _promedio(por_minuto(b, "lapsos") for b in base)
        n_lapsos = _num(m.get("lapsos"))
        if n_lapsos is not None and n_lapsos < 2:  # un lapso suelto no marca (en 1 min de modo demo sería "1 por minuto")
            r.append((0, "Varios lapsos de atención en la prueba PVT"))
        elif lpm is not None and lpm_b is not None:
            r.append((_escala(lpm - lpm_b, 1, 2), "Más lapsos de atención de lo habitual en la prueba PVT"))
        else:
            r.append((_escala(lpm, 1, 3), "Varios lapsos de atención en la prueba PVT"))
        r.append((min(1, _escala(por_minuto(m, "anticipadas"), 2, 99)), "Varias respuestas anticipadas en la prueba PVT"))
    elif tipo == "dsst":
        pm, pm_b = _num(m.get("por_minuto")), _promedio(_num(b.get("por_minuto")) for b in base)
        if pm is not None and pm_b:
            r.append((_escala(1 - pm / pm_b, 0.10, 0.20), "Menos aciertos de lo habitual en la prueba de símbolos"))
        elif pm is not None:
            r.append((2 if pm < 15 else 1 if pm < 25 else 0, "Pocos aciertos en la prueba de símbolos"))
        inc, inc_b = _num(m.get("incorrectas")), _promedio(_num(b.get("incorrectas")) for b in base)
        if inc is not None and inc_b is not None:
            r.append((1 if inc - inc_b >= 3 else 0, "Más errores de lo habitual en la prueba de símbolos"))
        else:
            r.append((1 if (inc or 0) >= 5 else 0, "Varios errores en la prueba de símbolos"))
    elif tipo == "cuestionario":
        kss = _num(m.get("kss"))
        if kss is not None:
            r.append((2, "Somnolencia muy alta según la escala de Karolinska") if kss >= 8 else
                     (1 if kss >= 7 else 0, "Somnolencia alta según la escala de Karolinska"))
        h, h_b = _num(m.get("horas_sueno")), _promedio(_num(b.get("horas_sueno")) for b in base)
        if h is not None and h_b is not None:
            falta = h_b - h
            r.append((2, "Muchas menos horas de sueño de lo habitual") if falta >= 3 else
                     (1 if falta >= 1.5 else 0, "Menos horas de sueño de lo habitual"))
        elif h is not None:
            r.append((2, "Menos de 4 horas de sueño") if h < 4 else (1 if h < 6 else 0, "Menos de 6 horas de sueño"))
    elif tipo == "voz":  # sin línea base de voz no hay comparación: la voz no cuenta
        if m.get("estado_voz") == "más cansada que su línea base":
            r.append((1, "Voz más cansada de lo habitual"))
        elif m.get("estado_voz") in ("normal", "con más energía que su línea base"):
            r.append((0, ""))
    elif tipo == "vision":
        cara = _num(m.get("cara_detectada_pct"))
        if cara is not None and cara < CARA_MIN_PCT:
            return r  # se vio poco la cara: la visión no cuenta como fuente evaluada
        ojos = not m.get("lentes")  # con lentes puestos el EAR puede salir mal: los ojos no cuentan
        p = _num(m.get("perclos")) if ojos else None
        p = p / 100 if p is not None and p > 1 else p  # por si llega en porcentaje
        p_b = _promedio((_num(b.get("perclos")) for b in base if not b.get("lentes")))
        p_b = p_b / 100 if p_b is not None and p_b > 1 else p_b
        if p is not None and p_b is not None:
            r.append((_escala(p - p_b, 0.05, 0.10), "Ojos cerrados más tiempo de lo habitual"))
        elif p is not None:
            r.append((_escala(p, 0.15, 0.25), "Ojos cerrados más tiempo de lo normal"))
        pm = _num(m.get("parpadeos_min")) if ojos else None
        pm_b = _promedio(_num(b.get("parpadeos_min")) for b in base if not b.get("lentes"))
        if pm is not None and pm_b:
            r.append((min(1, _escala(pm / pm_b - 1, 0.5, 99)), "Más parpadeos de lo habitual"))
        elif pm is not None:
            r.append((0, ""))  # medido, pero sin base no se juzga
        n_bost, bm = _num(m.get("bostezos")), _num(m.get("bostezos_min"))
        bm_b = _promedio(_num(b.get("bostezos_min")) for b in base)
        if n_bost is not None and n_bost < 2:  # un bostezo suelto no marca
            r.append((0, ""))
        elif bm is not None and bm_b is not None:
            r.append((1 if bm - bm_b >= 2 else 0, "Más bostezos de lo habitual"))
        elif bm is not None:
            r.append((1 if bm >= 2 else 0, "Bostezos durante la medición"))
        if rppg_confiable(m) and not hay_pulso_sensor:  # el pulso del sensor manda sobre el de la cámara
            hr = _num(m.get("pulso_rppg_lpm"))
            hr_b = _promedio(_num(b.get("pulso_rppg_lpm")) for b in base if rppg_confiable(b))
            if hr is not None and hr_b:
                r.append((_escala(hr / hr_b - 1, 0.15, 0.30), "Pulso en reposo más alto de lo habitual"))
            elif hr is not None:
                r.append((_escala(hr, 100, 120), "Pulso en reposo alto"))
    return r


def rppg_confiable(m: dict) -> bool:
    """El pulso por cámara solo cuenta si su calidad llega al mínimo (sin calidad, no cuenta)."""
    calidad = _num(m.get("calidad_rppg"))
    return calidad is not None and calidad >= CALIDAD_RPPG_MIN and _num(m.get("pulso_rppg_lpm")) is not None


def evaluar_spo2(lecturas: list[tuple[float, dict]], base_esp32: list[dict] | None = None) -> tuple[bool, float]:
    """(¿avisar?, segundos seguidos con el SpO2 bajo) con las lecturas del ESP32 de una sesión: (hora de llegada, mensaje).

    Bajo = SPO2_PUNTOS_BAJO o más por debajo del promedio de la línea base, o < SPO2_MINIMO_SIN_BASE sin línea base.
    Solo cuentan lecturas con dedo y calidad >= CALIDAD_ESP32_MIN: una sin dedo (o con mala calidad) o con el SpO2
    normal corta la racha; una sin valor de SpO2 (el sensor lo da cada ~4 s) no la corta ni la alarga."""
    base = _promedio(_num(b.get("spo2")) for b in (base_esp32 or []))
    racha_desde, mayor = None, 0.0
    for t, m in sorted(lecturas, key=lambda x: x[0]):
        calidad = _num(m.get("calidad"))
        if m.get("dedo") is not True or calidad is None or calidad < CALIDAD_ESP32_MIN:
            racha_desde = None
            continue
        v = _num(m.get("spo2"))
        if v is None:
            continue
        baja = v <= base - SPO2_PUNTOS_BAJO if base is not None else v < SPO2_MINIMO_SIN_BASE
        if not baja:
            racha_desde = None
            continue
        if racha_desde is None:
            racha_desde = t
        mayor = max(mayor, t - racha_desde)
    return mayor >= SPO2_SEGUNDOS, round(mayor, 1)


def evaluar(datos: dict[str, dict], base: dict[str, list[dict]] | None = None, aviso_spo2: bool = False) -> dict:
    """datos: {"pvt": mensaje, "cuestionario": mensaje, ...} de una sesión; base: línea base por tipo.

    Devuelve color, puntaje, motivos (hasta 3, frases neutras), accion, senales (puntos por fuente) y aviso_spo2.
    El aviso de SpO2 agrega MOTIVO_SPO2 pero no cambia el color ni el puntaje."""
    base = base or {}
    senales, motivos = {}, []
    hay_pulso_sensor = _num((datos.get("esp32") or {}).get("pulso_lpm")) is not None
    for tipo in TIPOS:
        if tipo not in datos:
            continue
        ind = _indicadores(tipo, datos[tipo], base.get(tipo, []), hay_pulso_sensor)
        if not ind:
            continue  # nada medible (voz sin línea base, visión sin PERCLOS): no cuenta como fuente evaluada
        senales[tipo] = max(p for p, _ in ind)
        motivos += [(p, texto) for p, texto in ind if p > 0]
    con_puntos = [p for p in senales.values() if p > 0]
    if any(p >= 2 for p in con_puntos) or len(con_puntos) >= 3:
        color = "rojo"
    elif con_puntos:
        color = "amarillo"
    else:
        color = "verde"
    puntaje = 1 - sum(senales.values()) / (2 * len(senales)) if senales else 1.0
    motivos.sort(key=lambda x: -x[0])  # los más fuertes primero (orden estable)
    textos = [t for _, t in motivos[:3]] + ([MOTIVO_SPO2] if aviso_spo2 else [])  # el aviso va aparte del color
    return {
        "color": color, "puntaje": round(max(0.0, puntaje), 2), "motivos": textos,
        "accion": ACCIONES[color], "senales": senales, "aviso_spo2": bool(aviso_spo2),
    }


def lectura_esp32_valida(m: dict) -> bool:
    """Con el dedo puesto y calidad suficiente (los mensajes viejos, sin esos campos, cuentan)."""
    if m.get("dedo") is False:
        return False
    calidad = _num(m.get("calidad"))
    return calidad is None or calidad >= CALIDAD_ESP32_MIN


def resumen_esp32(lecturas: list[dict]) -> dict:
    """Mediana de las lecturas válidas del ESP32 de una sesión (resiste lecturas sueltas malas)."""
    validas = [m for m in lecturas if lectura_esp32_valida(m)]

    def mediana(campo):
        vs = [x for x in (_num(m.get(campo)) for m in validas) if x is not None]
        return round(float(sorted(vs)[len(vs) // 2]), 1) if vs else None
    return {"pulso_lpm": mediana("pulso_lpm"), "spo2": mediana("spo2"), "hrv_rmssd_ms": mediana("hrv_rmssd_ms"),
            "lecturas": len(lecturas), "lecturas_validas": len(validas)}


# ---------------------------------------------------------------- línea base
def guardar_linea_base(persona: str, tipo: str, sesion: str, datos: dict, archivo: Path = ARCHIVO_BASE):
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with open(archivo, "a", encoding="utf-8") as f:
        f.write(json.dumps({"persona": persona, "tipo": tipo, "sesion": sesion, "datos": datos}, ensure_ascii=False) + "\n")


def leer_linea_base(persona: str, sin_sesion: str = "", archivo: Path = ARCHIVO_BASE) -> dict[str, list[dict]]:
    """Mediciones de línea base de la persona por tipo, sin las de la sesión indicada (la que se evalúa)."""
    base: dict[str, list[dict]] = {}
    if not archivo.exists():
        return base
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if fila.get("persona") == persona and fila.get("sesion") != sin_sesion and fila.get("tipo") in TIPOS:
            base.setdefault(fila["tipo"], []).append(fila.get("datos") or {})
    return base


# ---------------------------------------------------------------- servicio
class Coordinador:
    def __init__(self, cli: ClienteMQTT):
        self.cli = cli
        self.tareas: dict[str, str] = {}             # sesion -> tarea
        self.sesion_actual: dict[str, str] = {}      # persona -> última sesion
        self.sesiones: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def arrancar(self):
        self.cli.suscribir("apto/control/sesion", self._al_sesion)
        for tipo in TIPOS:
            self.cli.suscribir(f"apto/+/{tipo}", self._al_dato)

    def _al_sesion(self, _tema: str, d: dict):
        if d.get("persona") and d.get("sesion"):
            self.tareas[d["sesion"]] = d.get("tarea") or ""
            self.sesion_actual[d["persona"]] = d["sesion"]
            print(f"[coordinador] Sesión {d['sesion']}: {d['persona']}, {d.get('tarea') or '-'}")

    def _al_dato(self, tema_mqtt: str, d: dict):
        if d.get("reproducido"):  # registrador/reproducir.py ya trae la evaluación original: no se recalcula
            return
        persona, tipo = persona_de_tema(tema_mqtt), tema_mqtt.rsplit("/", 1)[-1]
        sesion = d.get("sesion") or self.sesion_actual.get(persona) or ""
        if not persona or persona == "control" or not sesion:
            return
        with self._lock:
            s = self.sesiones.setdefault((persona, sesion), {"datos": {}, "lista": False, "timer": None,
                                                             "inicio": time.time(), "esp32": [], "base_esp32": False})
            if tipo == "esp32":  # llega una lectura por segundo: se juntan (con su hora) y no se recalcula por cada una
                s["esp32"].append((time.time(), d))
                return
            s["datos"][tipo] = d
            if d.get("linea_base"):
                guardar_linea_base(persona, tipo, sesion, d)
            if tipo == "cuestionario":
                s["lista"] = True
            if s["lista"]:  # calcular (o recalcular) un momento después
                if s["timer"]:
                    s["timer"].cancel()
                s["timer"] = threading.Timer(ESPERA_S, self._publicar, args=(persona, sesion))
                s["timer"].daemon = True
                s["timer"].start()
        print(f"[coordinador] {persona}: llegó {tipo}{' (línea base)' if d.get('linea_base') else ''}")
        self._limpiar()

    def _publicar(self, persona: str, sesion: str):
        with self._lock:
            s = self.sesiones[(persona, sesion)]
            datos = dict(s["datos"])
            lecturas_esp32 = list(s["esp32"])
            if lecturas_esp32:
                datos["esp32"] = resumen_esp32([m for _, m in lecturas_esp32])
                # el ESP32 no marca línea base: se toma la de la sesión (la del cuestionario), una sola vez
                if (datos.get("cuestionario") or {}).get("linea_base") and not s["base_esp32"]:
                    guardar_linea_base(persona, "esp32", sesion, datos["esp32"])
                    s["base_esp32"] = True
        base = leer_linea_base(persona, sin_sesion=sesion)
        aviso, segundos_bajo = evaluar_spo2(lecturas_esp32, base.get("esp32"))
        r = evaluar(datos, base, aviso_spo2=aviso)
        if aviso:
            print(f"[coordinador] {persona}: SpO2 bajo durante {segundos_bajo:.0f} s seguidos -> aviso (no cambia el color)")
        ev = {"persona": persona, "sesion": sesion, "tarea": self.tareas.get(sesion, ""), **r, "provisional": True}
        self.cli.publicar(tema(persona, "evaluacion"), ev, retener=True)
        self.cli.publicar(tema(persona, "semaforo"), {"persona": persona, "sesion": sesion, "color": r["color"],
                                                      "provisional": True}, retener=True)
        print(f"[coordinador] {persona}: {r['color']} ({r['puntaje']}) {r['senales']} {r['motivos']}")

    def _limpiar(self):
        """Olvida las sesiones de hace más de 2 horas."""
        limite = time.time() - 7200
        with self._lock:
            for clave in [k for k, s in self.sesiones.items() if s["inicio"] < limite]:
                del self.sesiones[clave]


def main():
    cli = ClienteMQTT("coordinador")
    if not cli.conectar():
        print("El coordinador necesita MQTT. Revisen que Mosquitto esté corriendo.")
        return
    Coordinador(cli).arrancar()
    print("[coordinador] PROVISIONAL: esperando sesiones de la estación (Ctrl+C para salir).")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[coordinador] Saliendo.")
    finally:
        cli.cerrar()


if __name__ == "__main__":
    main()
