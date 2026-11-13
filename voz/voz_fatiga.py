"""Análisis de fatiga en la voz.

Graba (o lee un .wav) mientras la persona lee la frase fija, extrae rasgos de la voz con Praat
(parselmouth) y publica el resultado en MQTT: apto/{persona}/voz

Modos:
  python voz/voz_fatiga.py --listar                        lista los micrófonos
  python voz/voz_fatiga.py --persona eric                  graba y analiza una vez
  python voz/voz_fatiga.py --persona eric --linea-base     igual, marcado como línea base
  python voz/voz_fatiga.py --archivo grabacion.wav         analiza un .wav existente
  python voz/voz_fatiga.py --servicio                      espera órdenes por MQTT (apto/control/orden_voz)

Línea base: graben al menos 3 mediciones con --linea-base, con la persona descansada. Desde entonces
cada medición se compara con ellas y el mensaje lleva z_rasgos, indice_cansancio, estado_voz
("normal", "más cansada que su línea base", "con más energía que su línea base" o "sin línea base")
y motivos_voz. Es una sugerencia, no un diagnóstico: no detecta miedo ni emociones.

Orden por MQTT para el modo servicio (la envía el panel de Sebas):
  tema apto/control/orden_voz  ->  {"accion": "grabar", "persona": "eric", "segundos": 12, "linea_base": false}
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/

import numpy as np
import parselmouth
from parselmouth.praat import call

from comun import config
from comun.mqtt_cliente import ClienteMQTT, tema

FRASE = (
    "El astronauta revisa el sistema de soporte vital antes de iniciar la caminata espacial. "
    "Confirma la presión del traje, el nivel de oxígeno y la comunicación con la base."
)
CARPETA_DATOS = config.RAIZ / "datos" / "voz"
HISTORIAL = CARPETA_DATOS / "historial.jsonl"
F0_MIN, F0_MAX = 75, 500  # Hz, rango para voces de hombres y mujeres
FS = 16000

# --- Comparación con la línea base (sugerencia, no diagnóstico: no detecta miedo ni emociones) ---
# Sentido de cada rasgo: +1 si un valor más alto indica más cansancio, -1 si lo indica un valor más bajo.
SENTIDO_CANSANCIO = {
    "num_pausas": +1, "tiempo_habla_s": +1, "intensidad_media_db": -1, "f0_desv_hz": -1,
    "jitter_local": +1, "shimmer_local": +1, "hnr_db": -1,
}
MIN_LINEA_BASE = 3   # mediciones de línea base necesarias
UMBRAL_INDICE = 1.0  # índice > umbral: más cansada; < -umbral: con más energía. Un rasgo es motivo si pasa el umbral.
# Desviación mínima por rasgo: con pocas mediciones la desviación puede salir casi 0 y un cambio
# pequeño daría un puntaje z enorme.
DESV_MINIMA = {
    "num_pausas": 0.5, "tiempo_habla_s": 0.2, "intensidad_media_db": 1.0, "f0_desv_hz": 2.0,
    "jitter_local": 0.001, "shimmer_local": 0.005, "hnr_db": 0.5,
}
# Frases neutras, sin sujeto: (si el rasgo indica cansancio, si indica más energía)
MOTIVOS_VOZ = {
    "num_pausas": ("Más pausas de lo habitual", "Menos pausas de lo habitual"),
    "tiempo_habla_s": ("Lectura más lenta de lo habitual", "Lectura más rápida de lo habitual"),
    "intensidad_media_db": ("Voz más baja de lo habitual", "Voz más fuerte de lo habitual"),
    "f0_desv_hz": ("Tono más plano de lo habitual", "Tono más variado de lo habitual"),
    "jitter_local": ("Tono menos estable de lo habitual", "Tono más estable de lo habitual"),
    "shimmer_local": ("Volumen menos estable de lo habitual", "Volumen más estable de lo habitual"),
    "hnr_db": ("Voz más ronca de lo habitual", "Voz más clara de lo habitual"),
}


# ---------------------------------------------------------------- grabación
def listar_microfonos():
    import sounddevice as sd
    print(sd.query_devices())
    print("\nPongan el número del micrófono en MIC_DISPOSITIVO dentro de config.env.")


def grabar(segundos: int, destino: Path) -> Path:
    import sounddevice as sd
    import soundfile as sf

    dispositivo = config.get("MIC_DISPOSITIVO")
    dispositivo = int(dispositivo) if dispositivo.isdigit() else None
    print("\nLee en voz alta, con tono normal:\n")
    print(f"   «{FRASE}»\n")
    for n in (3, 2, 1):
        print(f"   Empieza en {n}...", end="\r")
        time.sleep(1)
    print(f"   Grabando {segundos} s...          ")
    audio = sd.rec(int(segundos * FS), samplerate=FS, channels=1, dtype="float32", device=dispositivo)
    sd.wait()
    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destino, audio, FS)
    print("   Listo.\n")
    return destino


# ---------------------------------------------------------------- análisis
def _seguro(valor) -> float | None:
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) or np.isinf(v) else round(v, 4)


def analizar(ruta_wav: Path) -> dict:
    """Devuelve los rasgos de la voz de un archivo .wav."""
    snd = parselmouth.Sound(str(ruta_wav))
    if snd.n_channels > 1:
        snd = snd.convert_to_mono()
    duracion = snd.get_total_duration()

    # Tono (F0)
    pitch = snd.to_pitch(time_step=0.01, pitch_floor=F0_MIN, pitch_ceiling=F0_MAX)
    f0 = pitch.selected_array["frequency"]
    f0 = f0[f0 > 0]
    voz_detectada = len(f0) > 10

    # Jitter, shimmer y HNR (medidas clásicas de Praat)
    jitter = shimmer = hnr = None
    if voz_detectada:
        pp = call(snd, "To PointProcess (periodic, cc)", F0_MIN, F0_MAX)
        jitter = call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        harm = call(snd, "To Harmonicity (cc)", 0.01, F0_MIN, 0.1, 1.0)
        hnr = call(harm, "Get mean", 0, 0)

    # Intensidad y pausas: tramos más de 25 dB por debajo del máximo son silencio
    inten = snd.to_intensity(minimum_pitch=F0_MIN, time_step=0.01)
    valores_db = inten.values[0]
    paso = inten.time_step
    umbral = np.max(valores_db) - 25 if len(valores_db) else 0
    habla = valores_db > umbral
    # Se empieza a contar desde la primera trama con habla: el silencio inicial no es una pausa.
    # El silencio final tampoco cuenta, porque una pausa solo se registra cuando el habla vuelve.
    primero = int(np.argmax(habla)) if np.any(habla) else len(habla)
    pausas, actual = [], 0
    for es_habla in habla[primero:]:
        if not es_habla:
            actual += 1
        else:
            if actual * paso >= 0.25:  # pausas de 250 ms o más
                pausas.append(actual * paso)
            actual = 0
    tiempo_habla = float(np.sum(habla)) * paso

    return {
        "voz_detectada": voz_detectada,
        "duracion_s": _seguro(duracion),
        "f0_media_hz": _seguro(np.mean(f0)) if voz_detectada else None,
        "f0_desv_hz": _seguro(np.std(f0)) if voz_detectada else None,
        "jitter_local": _seguro(jitter),
        "shimmer_local": _seguro(shimmer),
        "hnr_db": _seguro(hnr),
        "intensidad_media_db": _seguro(np.mean(valores_db[habla])) if np.any(habla) else None,
        "tiempo_habla_s": _seguro(tiempo_habla),
        "num_pausas": len(pausas),
        "tiempo_pausas_s": _seguro(sum(pausas)),
        "proporcion_pausas": _seguro(sum(pausas) / tiempo_habla) if tiempo_habla > 0 else None,
    }


# ---------------------------------------------------------------- línea base
def leer_linea_base(persona: str, historial: Path = HISTORIAL) -> list[dict]:
    """Mediciones de la persona marcadas con linea_base (y con voz detectada) en historial.jsonl."""
    if not historial.exists():
        return []
    base = []
    with open(historial, encoding="utf-8") as f:
        for linea in f:
            try:
                m = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if m.get("persona") == persona and m.get("linea_base") and m.get("voz_detectada"):
                base.append(m)
    return base


def comparar_con_linea_base(rasgos: dict, base: list[dict]) -> dict:
    """Puntaje z de cada rasgo frente a la línea base, índice de cansancio, estado y motivos.

    indice_cansancio = promedio de los z con el signo de SENTIDO_CANSANCIO: positivo = más cansancio.
    """
    resultado = {"linea_base_n": len(base), "z_rasgos": {}, "indice_cansancio": None,
                 "estado_voz": "sin línea base", "motivos_voz": []}
    if len(base) < MIN_LINEA_BASE:
        return resultado
    if not rasgos.get("voz_detectada"):
        resultado["estado_voz"] = "sin voz detectada"
        return resultado

    cansancio = {}  # z con el signo puesto: positivo = más cansancio
    for rasgo, sentido in SENTIDO_CANSANCIO.items():
        valores = [m[rasgo] for m in base if m.get(rasgo) is not None]
        actual = rasgos.get(rasgo)
        if actual is None or len(valores) < MIN_LINEA_BASE:
            continue
        desv = max(float(np.std(valores, ddof=1)), DESV_MINIMA[rasgo])
        z = (actual - float(np.mean(valores))) / desv
        resultado["z_rasgos"][rasgo] = round(z, 2)
        cansancio[rasgo] = sentido * z
    if not cansancio:
        resultado["estado_voz"] = "sin voz detectada"
        return resultado

    indice = float(np.mean(list(cansancio.values())))
    resultado["indice_cansancio"] = round(indice, 2)
    if indice > UMBRAL_INDICE:
        resultado["estado_voz"], signo, cual = "más cansada que su línea base", 1, 0
    elif indice < -UMBRAL_INDICE:
        resultado["estado_voz"], signo, cual = "con más energía que su línea base", -1, 1
    else:
        resultado["estado_voz"] = "normal"
        return resultado
    # Motivos: hasta 2 rasgos que más pesaron en el sentido del estado y que pasan el umbral.
    orden = sorted(cansancio, key=lambda r: signo * cansancio[r], reverse=True)
    resultado["motivos_voz"] = [MOTIVOS_VOZ[r][cual] for r in orden[:2] if signo * cansancio[r] > UMBRAL_INDICE]
    return resultado


# ---------------------------------------------------------------- flujo completo
def evaluar(persona: str, segundos: int, linea_base: bool, cli: ClienteMQTT | None,
            archivo: Path | None = None, sesion: str = "") -> dict:
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    if archivo is None:
        archivo = grabar(segundos, CARPETA_DATOS / persona / f"{marca}.wav")
    rasgos = analizar(archivo)
    mensaje = {
        "persona": persona,
        "sesion": sesion or marca,
        "linea_base": linea_base,
        "archivo": archivo.name,
        **rasgos,
        # se compara con la línea base guardada antes de esta medición
        **comparar_con_linea_base(rasgos, leer_linea_base(persona)),
    }
    if not rasgos["voz_detectada"]:
        mensaje["aviso"] = "No se detectó voz: revisen el micrófono o la distancia."
        print("AVISO: no se detectó voz en la grabación.")

    # guardar copia local (sirve como respaldo y para calcular la línea base)
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(mensaje, ensure_ascii=False) + "\n")

    print(json.dumps(mensaje, indent=2, ensure_ascii=False))
    if cli:
        cli.publicar(tema(persona, "voz"), mensaje)
    return mensaje


def modo_servicio(cli: ClienteMQTT):
    print("Modo servicio: esperando órdenes en apto/control/orden_voz (Ctrl+C para salir)")
    pendientes: list[dict] = []
    cli.suscribir("apto/control/orden_voz", lambda _t, d: pendientes.append(d))
    try:
        while True:
            if pendientes:
                orden = pendientes.pop(0)
                if orden.get("accion") == "grabar":
                    persona = orden.get("persona") or config.get("PERSONA", "bri")
                    cli.publicar("apto/control/estado_voz", {"persona": persona, "estado": "grabando"})
                    evaluar(persona, int(orden.get("segundos", config.get_int("VOZ_SEGUNDOS", 12))),
                            bool(orden.get("linea_base", False)), cli, sesion=orden.get("sesion", ""))
                    cli.publicar("apto/control/estado_voz", {"persona": persona, "estado": "listo"})
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


def main():
    ap = argparse.ArgumentParser(description="Análisis de fatiga en la voz")
    ap.add_argument("--persona", default=config.get("PERSONA", "bri"))
    ap.add_argument("--segundos", type=int, default=config.get_int("VOZ_SEGUNDOS", 12))
    ap.add_argument("--linea-base", action="store_true", help="marca esta medición como línea base")
    ap.add_argument("--archivo", type=Path, help="analiza un .wav en vez de grabar")
    ap.add_argument("--servicio", action="store_true", help="espera órdenes por MQTT")
    ap.add_argument("--sin-mqtt", action="store_true", help="no conecta a MQTT (solo muestra el resultado)")
    ap.add_argument("--listar", action="store_true", help="lista los micrófonos")
    args = ap.parse_args()

    if args.listar:
        listar_microfonos()
        return

    cli = None
    if not args.sin_mqtt:
        cli = ClienteMQTT("voz")
        if not cli.conectar() and args.servicio:
            print("El modo servicio necesita MQTT. Revisen que Mosquitto esté corriendo.")
            return

    if args.servicio:
        modo_servicio(cli)
    else:
        evaluar(args.persona, args.segundos, args.linea_base, cli, args.archivo)
        if cli:
            time.sleep(0.5)  # dar tiempo a que salga el mensaje
            cli.cerrar()


if __name__ == "__main__":
    main()
