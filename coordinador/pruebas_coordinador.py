"""Prueba simple de las reglas del coordinador provisional (datos inventados; no necesita MQTT).

  python coordinador/pruebas_coordinador.py

Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coordinador_provisional import evaluar, guardar_linea_base, leer_linea_base  # noqa: E402

PVT_BIEN = {"rt_media_ms": 280, "lapsos": 0, "anticipadas": 0, "duracion_s": 180, "lapsos_por_min": 0, "anticipadas_por_min": 0}
DSST_BIEN = {"correctas": 60, "incorrectas": 1, "por_minuto": 40, "duracion_s": 90}
CUEST_BIEN = {"kss": 3, "horas_sueno": 7.5}


def sesion(**cambios) -> dict:
    """Una sesión normal; cada argumento reemplaza o agrega campos de una fuente."""
    datos = {"pvt": dict(PVT_BIEN), "dsst": dict(DSST_BIEN), "cuestionario": dict(CUEST_BIEN),
             "voz": {"estado_voz": "sin línea base"}}
    for tipo, campos in cambios.items():
        datos[tipo] = {**datos.get(tipo, {}), **campos}
    return datos


BASE = {"pvt": [{"rt_media_ms": 250, "lapsos_por_min": 0}, {"rt_media_ms": 250, "lapsos_por_min": 0}],
        "dsst": [{"por_minuto": 45, "incorrectas": 1}], "cuestionario": [{"horas_sueno": 8}]}

# (nombre, datos, línea base, color esperado, motivos que deben estar)
CASOS = [
    ("todo normal, sin línea base", sesion(), None, "verde", []),
    ("Karolinska 7", sesion(cuestionario={"kss": 7}), None, "amarillo", ["Somnolencia alta según la escala de Karolinska"]),
    ("3,5 h de sueño (2 puntos)", sesion(cuestionario={"horas_sueno": 3.5}), None, "rojo", ["Menos de 4 horas de sueño"]),
    ("3 fuentes moderadas", sesion(pvt={"rt_media_ms": 360}, dsst={"por_minuto": 22}, cuestionario={"kss": 7}), None, "rojo",
     ["Reacción lenta en la prueba PVT", "Pocos aciertos en la prueba de símbolos"]),
    ("PVT modo demo: 2 lapsos en 1 min", sesion(pvt={"lapsos": 2, "duracion_s": 60, "lapsos_por_min": 2}), None, "amarillo",
     ["Varios lapsos de atención en la prueba PVT"]),
    ("PVT modo demo: 1 lapso suelto no marca", sesion(pvt={"lapsos": 1, "duracion_s": 60, "lapsos_por_min": 1}), None, "verde", []),
    ("con base: reacción +20 %", sesion(pvt={"rt_media_ms": 300}), BASE, "amarillo",
     ["Reacción más lenta de lo habitual en la prueba PVT"]),
    ("con base: 4 h menos de sueño", sesion(cuestionario={"horas_sueno": 4}), BASE, "rojo",
     ["Muchas menos horas de sueño de lo habitual"]),
    ("con base: todo igual", sesion(pvt={"rt_media_ms": 255}, dsst={"por_minuto": 44}, cuestionario={"horas_sueno": 7.5}), BASE,
     "verde", []),
    ("voz cansada (señal débil)", sesion(voz={"estado_voz": "más cansada que su línea base"}), None, "amarillo",
     ["Voz más cansada de lo habitual"]),
    ("visión PERCLOS 0,3", sesion(vision={"perclos": 0.3}), None, "rojo", ["Ojos cerrados más tiempo de lo normal"]),
    ("visión: pulso 110 con buena calidad", sesion(vision={"perclos": 0.05, "pulso_rppg_lpm": 110, "calidad_rppg": 0.8}),
     None, "amarillo", ["Pulso en reposo alto"]),
    ("visión: 3 bostezos en 1 min", sesion(vision={"perclos": 0.05, "bostezos": 3, "bostezos_min": 3.0}), None, "amarillo",
     ["Bostezos durante la medición"]),
    ("visión: 1 bostezo suelto no marca", sesion(vision={"perclos": 0.05, "bostezos": 1, "bostezos_min": 1.0}), None,
     "verde", []),
    ("sensor 75 lpm manda sobre la cámara (130 con buena calidad)",
     sesion(vision={"perclos": 0.05, "pulso_rppg_lpm": 130, "calidad_rppg": 0.9}, esp32={"pulso_lpm": 75}), None, "verde", []),
    ("sensor 110 lpm", sesion(esp32={"pulso_lpm": 110}), None, "amarillo", ["Pulso en reposo alto"]),
    ("sensor: HRV 30 % más baja que la base", sesion(esp32={"pulso_lpm": 72, "hrv_rmssd_ms": 31.5}),
     {"esp32": [{"pulso_lpm": 70, "hrv_rmssd_ms": 45}]}, "amarillo", ["Variabilidad del pulso más baja de lo habitual"]),
    ("sensor: HRV sin base no se juzga", sesion(esp32={"pulso_lpm": 72, "hrv_rmssd_ms": 15}), None, "verde", []),
    ("visión: cara vista el 30 % del tiempo no cuenta", sesion(vision={"perclos": 0.4, "cara_detectada_pct": 30}),
     None, "verde", []),
    ("visión: pulso 130 con mala calidad no cuenta", sesion(vision={"perclos": 0.05, "pulso_rppg_lpm": 130, "calidad_rppg": 0.3}),
     None, "verde", []),
    ("visión con base: +60 % parpadeos", sesion(vision={"perclos": 0.05, "parpadeos_min": 24}),
     {"vision": [{"perclos": 0.05, "parpadeos_min": 15}]}, "amarillo", ["Más parpadeos de lo habitual"]),
    ("visión con base: pulso +20 % (base de mala calidad ignorada)",
     sesion(vision={"perclos": 0.05, "pulso_rppg_lpm": 84, "calidad_rppg": 0.9}),
     {"vision": [{"perclos": 0.05, "pulso_rppg_lpm": 70, "calidad_rppg": 0.9},
                 {"perclos": 0.05, "pulso_rppg_lpm": 110, "calidad_rppg": 0.2}]},
     "amarillo", ["Pulso en reposo más alto de lo habitual"]),
    ("solo el cuestionario (DSST omitido)", {"cuestionario": {"kss": 4, "horas_sueno": 7}}, None, "verde", []),
]


def main() -> int:
    fallas = 0
    for nombre, datos, base, color, motivos in CASOS:
        r = evaluar(datos, base)
        ok = (r["color"] == color and all(m in r["motivos"] for m in motivos) and len(r["motivos"]) <= 3
              and (r["motivos"] or color == "verde") and 0 <= r["puntaje"] <= 1 and r["accion"])
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {nombre}: {r['color']} {r['puntaje']} {r['motivos']}")
        if not ok:
            print(f"       esperado: {color} con {motivos}; señales {r['senales']}")

    # la voz sin línea base no cuenta como fuente; con "normal" sí (0 puntos)
    sin = evaluar(sesion())["senales"]
    con = evaluar(sesion(voz={"estado_voz": "normal"}))["senales"]
    ok = "voz" not in sin and con.get("voz") == 0
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  voz sin línea base no cuenta; voz normal cuenta con 0: {sin} / {con}")

    # línea base guardada: se excluye la sesión que se está evaluando
    with tempfile.TemporaryDirectory() as carpeta:
        archivo = Path(carpeta) / "linea_base.jsonl"
        guardar_linea_base("sebas", "pvt", "s1", {"rt_media_ms": 250}, archivo)
        guardar_linea_base("sebas", "pvt", "s2", {"rt_media_ms": 260}, archivo)
        guardar_linea_base("bri", "pvt", "s3", {"rt_media_ms": 300}, archivo)
        base = leer_linea_base("sebas", sin_sesion="s2", archivo=archivo)
        ok = [b["rt_media_ms"] for b in base.get("pvt", [])] == [250]
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  línea base de sebas sin la sesión evaluada: {base}")

    # El ESP32 manda una lectura por segundo: se juntan (mediana) y no reinician la espera del cálculo.
    from coordinador_provisional import Coordinador

    class CliFalso:
        def __init__(self):
            self.mensajes = []

        def publicar(self, tema, datos, retener=False):
            self.mensajes.append((tema, datos))

        def suscribir(self, *a, **k):
            pass

    cli = CliFalso()
    coord = Coordinador(cli)
    coord._al_sesion("apto/control/sesion", {"persona": "sebas", "tarea": "caminata espacial", "sesion": "s9"})
    for pulso in (72, 74, 140, 73):  # una lectura suelta mala (140) no debe pesar
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": pulso, "dedo": True, "calidad": 0.9})
    for _ in range(3):  # sin dedo o con mala calidad: no cuentan
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": 130, "dedo": False, "calidad": 0})
        coord._al_dato("apto/sebas/esp32", {"persona": "sebas", "pulso_lpm": 130, "dedo": True, "calidad": 0.2})
    coord._al_dato("apto/sebas/cuestionario", {"persona": "sebas", "sesion": "s9", "kss": 3, "horas_sueno": 8})
    s = coord.sesiones[("sebas", "s9")]
    s["timer"].cancel()
    coord._publicar("sebas", "s9")
    ev = next(d for t, d in cli.mensajes if t == "apto/sebas/evaluacion")
    ok = len(s["esp32"]) == 10 and ev["color"] == "verde" and "esp32" in ev["senales"]
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  ESP32: 10 lecturas juntadas, solo 4 válidas (con dedo y calidad) en la mediana "
          f"-> {ev['color']} {ev['senales']}")

    total = len(CASOS) + 3
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
