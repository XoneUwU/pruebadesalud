"""Simulador: publica evaluaciones y datos falsos para probar sin esperar a los demás módulos.

  python herramientas/simulador.py                 menú: 1 verde, 2 amarillo, 3 rojo
  python herramientas/simulador.py --auto 20       publica una evaluación al azar cada 20 s
  python herramientas/simulador.py --esp32 40 --spo2 89   40 lecturas del ESP32 (1 por segundo) con SpO2 ~89

Los datos son FALSOS: sirven solo para probar el copiloto y los paneles.
"""
import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comun import config
from comun.mqtt_cliente import ClienteMQTT, tema

CASOS = {
    "verde": {
        "puntaje": 0.88, "motivos": [],
        "accion": "Puede realizar la tarea",
        "pesos": {"sueno": 0.2, "pvt": 0.2, "hrv": 0.2, "perclos": 0.2, "voz": 0.2},
    },
    "amarillo": {
        "puntaje": 0.62,
        # Motivos como frases neutras, sin sujeto: el copiloto los lee tras "tu resultado... Motivos:"
        "motivos": ["Menos horas de sueño de lo habitual", "Reacción más lenta en la prueba PVT"],
        "accion": "Reasignar la tarea o hacerla en pareja, y descansar antes",
        "pesos": {"sueno": 0.35, "pvt": 0.25, "hrv": 0.15, "perclos": 0.15, "voz": 0.10},
    },
    "rojo": {
        "puntaje": 0.31,
        "motivos": ["Muchas menos horas de sueño de lo habitual", "Ojos cerrados más tiempo de lo normal",
                    "Varios lapsos de atención en la prueba PVT"],
        "accion": "No realizar la tarea crítica; reasignarla e informar al comandante",
        "pesos": {"sueno": 0.30, "perclos": 0.30, "pvt": 0.25, "hrv": 0.10, "voz": 0.05},
    },
}


def publicar_evaluacion(cli: ClienteMQTT, persona: str, color: str, tarea: str, puntaje: float | None = None):
    msg = {"persona": persona, "sesion": f"sim-{datetime.now():%H%M%S}", "tarea": tarea,
           "color": color, "simulado": True, **CASOS[color]}
    if puntaje is not None:
        msg["puntaje"] = puntaje
    cli.publicar(tema(persona, "evaluacion"), msg, retener=True)
    cli.publicar(tema(persona, "semaforo"), {"persona": persona, "color": color, "simulado": True}, retener=True)
    print(f"Publicado: {persona} -> {color}")


def publicar_esp32(cli: ClienteMQTT, persona: str, spo2: float | None = None):
    cli.publicar(tema(persona, "esp32"), {
        "persona": persona, "simulado": True,
        "pulso_lpm": round(random.gauss(72, 4)), "hrv_rmssd_ms": round(random.gauss(42, 6), 1),
        "spo2": round(random.gauss(spo2 if spo2 is not None else 97.5, 0.4), 1),
        "movimiento": round(abs(random.gauss(0.02, 0.01)), 3), "dedo": True, "calidad": 0.9,
    })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default=config.get("PERSONA", "bri"))
    ap.add_argument("--tarea", default="caminata espacial")
    ap.add_argument("--auto", type=int, default=0, help="segundos entre evaluaciones al azar")
    ap.add_argument("--esp32", type=int, default=0,
                    help="solo publica lecturas del ESP32 (una por segundo) durante estos segundos y termina")
    ap.add_argument("--spo2", type=float, default=None, help="SpO2 de las lecturas del ESP32 (por defecto ~97,5)")
    args = ap.parse_args()

    cli = ClienteMQTT("simulador")
    if not cli.conectar():
        return
    if args.esp32:  # p. ej. --esp32 40 --spo2 89 para probar el aviso de oxígeno bajo
        print(f"Publicando {args.esp32} lecturas del ESP32 de {args.persona} (SpO2 ~{args.spo2 or 97.5})")
        for _ in range(args.esp32):
            publicar_esp32(cli, args.persona, args.spo2)
            time.sleep(1)
    elif args.auto:
        print(f"Publicando cada {args.auto} s (Ctrl+C para salir)")
        try:
            while True:
                for _ in range(args.auto):
                    publicar_esp32(cli, args.persona)
                    time.sleep(1)
                publicar_evaluacion(cli, args.persona, random.choice(list(CASOS)), args.tarea)
        except KeyboardInterrupt:
            pass
    else:
        persona = args.persona
        print("1 = verde, 2 = amarillo, 3 = rojo, t = tripulación de ejemplo, p nombre = cambiar persona, q = salir")
        while True:
            op = input(f"[{persona}] > ").lstrip("\ufeff").strip().lower()  # \ufeff: BOM de PowerShell
            if op == "q":
                break
            if op == "t":  # tripulación de ejemplo para probar «¿quién está más apto?»
                for p, c, pts in (("bri", "amarillo", 0.62), ("erick", "verde", 0.88),
                                  ("sebas", "verde", 0.81), ("adrian", "amarillo", 0.58),
                                  ("danilo", "rojo", 0.31)):
                    publicar_evaluacion(cli, p, c, args.tarea, pts)
                continue
            if op.startswith("p "):
                persona = op[2:].strip()
                cli.publicar("apto/control/sesion", {"persona": persona, "tarea": args.tarea})
                continue
            color = {"1": "verde", "2": "amarillo", "3": "rojo"}.get(op)
            if color:
                publicar_evaluacion(cli, persona, color, args.tarea)
    time.sleep(0.5)
    cli.cerrar()


if __name__ == "__main__":
    main()
