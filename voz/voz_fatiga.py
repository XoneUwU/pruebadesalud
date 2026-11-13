"""Análisis de fatiga en la voz.

Graba (o lee un .wav) mientras la persona lee la frase fija, extrae rasgos de la voz con Praat
(parselmouth) y publica el resultado en MQTT: apto/{persona}/voz

Modos:
  python voz/voz_fatiga.py --listar                        lista los micrófonos
  python voz/voz_fatiga.py --persona eric                  graba y analiza una vez
  python voz/voz_fatiga.py --persona eric --linea-base     igual, marcado como línea base
  python voz/voz_fatiga.py --archivo grabacion.wav         analiza un .wav existente
  python voz/voz_fatiga.py --servicio                      espera órdenes por MQTT (apto/control/orden_voz)

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
F0_MIN, F0_MAX = 75, 500  # Hz, rango para voces de hombres y mujeres
FS = 16000


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
    }
    if not rasgos["voz_detectada"]:
        mensaje["aviso"] = "No se detectó voz: revisen el micrófono o la distancia."
        print("AVISO: no se detectó voz en la grabación.")

    # guardar copia local (sirve como respaldo y para calcular la línea base)
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(CARPETA_DATOS / "historial.jsonl", "a", encoding="utf-8") as f:
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
                    persona = orden.get("persona") or config.get("PERSONA", "xone")
                    cli.publicar("apto/control/estado_voz", {"persona": persona, "estado": "grabando"})
                    evaluar(persona, int(orden.get("segundos", config.get_int("VOZ_SEGUNDOS", 12))),
                            bool(orden.get("linea_base", False)), cli, sesion=orden.get("sesion", ""))
                    cli.publicar("apto/control/estado_voz", {"persona": persona, "estado": "listo"})
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


def main():
    ap = argparse.ArgumentParser(description="Análisis de fatiga en la voz")
    ap.add_argument("--persona", default=config.get("PERSONA", "xone"))
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
