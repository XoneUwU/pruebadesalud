"""Prueba simple de «soy X» y del resumen de la tripulación (no necesita MQTT, Ollama ni micrófono).

  python copiloto/pruebas_identificacion.py

Usa el copiloto real sin MQTT, sin modelo y sin voz, con un cliente falso que guarda lo que se
publicaría. Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import argparse
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from copiloto import AVISO, Copiloto, resumen_tripulacion  # noqa: E402

TRIPULACION = ["bri", "danilo", "sebas", "erick", "adrian"]
TAREA = "caminata espacial"


def ev(persona: str, color: str, puntaje: float) -> dict:
    return {"persona": persona, "color": color, "puntaje": puntaje, "tarea": TAREA}


EVALUACIONES = {  # sebas no tiene evaluación, para probar «Todavía no tienes una evaluación.»
    "bri": ev("bri", "amarillo", 0.62), "erick": ev("erick", "verde", 0.88),
    "adrian": ev("adrian", "amarillo", 0.58), "danilo": ev("danilo", "rojo", 0.31),
}


class CliFalso:
    def __init__(self):
        self.mensajes: list[tuple[str, dict]] = []

    def publicar(self, tema: str, datos: dict, retener: bool = False):
        self.mensajes.append((tema, datos))


def nuevo_copiloto() -> Copiloto:
    args = argparse.Namespace(persona="bri", texto=True, sin_voz=True, sin_llm=True, sin_mqtt=True, sin_auto=True)
    with contextlib.redirect_stdout(io.StringIO()):
        cop = Copiloto(args)
    cop.tripulacion = list(TRIPULACION)
    cop.evaluaciones = dict(EVALUACIONES)
    cop.cli = CliFalso()
    return cop


# (pregunta, persona activa esperada, modo esperado, texto esperado o None, sesión publicada esperada o None)
CASOS = [
    # --- casos pedidos
    ("Soy Erik", "erick", "identificacion",
     "Hola Erick. Tu último resultado es verde. Pregúntame si quieres los detalles.",
     {"persona": "erick", "tarea": TAREA}),
    ("habla Sebas", "sebas", "identificacion", "Hola Sebas. Todavía no tienes una evaluación.",
     {"persona": "sebas", "tarea": TAREA}),
    ("soy Diego", "bri", "identificacion",
     "No reconozco ese nombre. La tripulación es: Bri, Danilo, Sebas, Erick y Adrian.", None),
    ("Soy Erick, me falta el aire", "erick", "alarma", None, {"persona": "erick", "tarea": TAREA}),
    # --- casos extra
    ("Aquí Brí.", "bri", "identificacion",
     "Hola Bri. Tu último resultado es amarillo. Pregúntame si quieres los detalles.",
     {"persona": "bri", "tarea": TAREA}),
    ("habla más despacio", "bri", None, None, None),  # nombre desconocido y más texto: no es identificación
]


def main() -> int:
    fallas = 0
    for pregunta, persona, modo, texto, sesion in CASOS:
        cop = nuevo_copiloto()
        with contextlib.redirect_stdout(io.StringIO()):
            obtenido = cop.responder(pregunta)
        copiloto = [d for t, d in cop.cli.mensajes if t.endswith("/copiloto")]
        sesiones = [d for t, d in cop.cli.mensajes if t == "apto/control/sesion"]
        modo_obt = copiloto[-1]["modo"] if copiloto else None
        ok = (cop.persona == persona and len(copiloto) == 1 and copiloto[0]["persona"] == persona
              and (modo_obt == modo if modo else modo_obt != "identificacion")
              and (texto is None or obtenido == texto)
              and sesiones == ([sesion] if sesion else []))
        if modo == "alarma":
            ok = ok and AVISO in obtenido
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  «{pregunta}» -> persona={cop.persona}  modo={modo_obt}\n"
              f"       {obtenido}")
        if not ok:
            print(f"       esperado: persona={persona} modo={modo} texto={texto!r} sesión={sesion}  "
                  f"publicado={cop.cli.mensajes}")

    # Tripulación agrupada por color, con Bri como persona activa.
    print("\n--- tripulación agrupada ---")
    grupos = [
        (EVALUACIONES | {"sebas": ev("sebas", "verde", 0.81)}, "bri",
         "La persona más apta para la caminata espacial es Erick, en verde. También está en verde Sebas. "
         "Tú y Adrian están en amarillo, y Danilo está en rojo."),
        ({"erick": ev("erick", "verde", 0.88), "bri": ev("bri", "verde", 0.80), "sebas": ev("sebas", "verde", 0.81),
          "danilo": ev("danilo", "rojo", 0.31)}, "bri",
         "La persona más apta para la caminata espacial es Erick, en verde. Tú y Sebas también están en verde. "
         "Danilo está en rojo."),
        ({"erick": ev("erick", "verde", 0.88), "bri": ev("bri", "amarillo", 0.62),
          "danilo": ev("danilo", "rojo", 0.31)}, "bri",
         "La persona más apta para la caminata espacial es Erick, en verde. Tú estás en amarillo y Danilo está "
         "en rojo."),
    ]
    for evaluaciones, activa, esperado in grupos:
        obtenido = resumen_tripulacion(evaluaciones, TAREA, activa)
        ok = obtenido == esperado
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {obtenido}")
        if not ok:
            print(f"       esperado: {esperado}")

    total = len(CASOS) + len(grupos)
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
