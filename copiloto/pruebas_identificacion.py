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

TRIPULACION = ["bri", "danilo", "sebas", "eric", "adrian"]
TAREA = "caminata espacial"


def ev(persona: str, color: str, puntaje: float) -> dict:
    return {"persona": persona, "color": color, "puntaje": puntaje, "tarea": TAREA}


EVALUACIONES = {  # sebas no tiene evaluación, para probar «Todavía no tienes una evaluación.»
    "bri": ev("bri", "amarillo", 0.62), "eric": ev("eric", "verde", 0.88),
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
    ("Soy Erik", "eric", "identificacion",
     "Hola Eric. Tu último resultado es verde. Pregúntame si quieres los detalles.",
     {"persona": "eric", "tarea": TAREA}),
    ("habla Sebas", "sebas", "identificacion", "Hola Sebas. Todavía no tienes una evaluación.",
     {"persona": "sebas", "tarea": TAREA}),
    ("soy Diego", "bri", "identificacion",
     "No reconozco ese nombre. La tripulación es: Bri, Danilo, Sebas, Eric y Adrian.", None),
    ("Soy Eric, me falta el aire", "eric", "alarma", None, {"persona": "eric", "tarea": TAREA}),
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
         "La persona más apta para la caminata espacial es Eric, en verde. También está en verde Sebas. "
         "Tú y Adrian están en amarillo, y Danilo está en rojo."),
        ({"eric": ev("eric", "verde", 0.88), "bri": ev("bri", "verde", 0.80), "sebas": ev("sebas", "verde", 0.81),
          "danilo": ev("danilo", "rojo", 0.31)}, "bri",
         "La persona más apta para la caminata espacial es Eric, en verde. Tú y Sebas también están en verde. "
         "Danilo está en rojo."),
        ({"eric": ev("eric", "verde", 0.88), "bri": ev("bri", "amarillo", 0.62),
          "danilo": ev("danilo", "rojo", 0.31)}, "bri",
         "La persona más apta para la caminata espacial es Eric, en verde. Tú estás en amarillo y Danilo está "
         "en rojo."),
    ]
    for evaluaciones, activa, esperado in grupos:
        obtenido = resumen_tripulacion(evaluaciones, TAREA, activa)
        ok = obtenido == esperado
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {obtenido}")
        if not ok:
            print(f"       esperado: {esperado}")

    # Preguntar en voz alta desde la estación (botón Hablar).
    print("\n--- escuchar por voz ---")
    from habla import decidir_corte
    ruido, voz = [0.002] * 6, [0.05]
    casos_corte = [
        ("habla y se calla 1,2 s", ruido + voz * 30 + [0.002] * 24, "fin"),
        ("habla y lleva 0,5 s callado", ruido + voz * 30 + [0.002] * 10, None),
        ("5 s sin hablar", ruido + [0.003] * 94, "sin_voz"),
        ("todavía no habla (2 s)", ruido + [0.003] * 34, None),
    ]
    for nombre, volumenes, esperado in casos_corte:
        r = decidir_corte(volumenes)
        ok = r == esperado
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  cortar la escucha: {nombre} -> {r}")
    cop = nuevo_copiloto()  # abierto con --texto: no tiene Whisper
    cop._escuchar_panel("bri", {"segundos_max": 5})
    estados = [d for t, d in cop.cli.mensajes if t == "apto/control/estado_escucha"]
    ok = len(estados) == 1 and estados[0]["estado"] == "error" and "modo texto" in estados[0]["motivo"]
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  en modo texto avisa que no puede escuchar: {estados[-1]['motivo'] if estados else '-'}")

    # Aviso de SpO2 en el resumen: aparte de los motivos y sin «señales en rango habitual».
    print("\n--- aviso de SpO2 ---")
    from copiloto import AVISO_SPO2, resumen
    motivo = "Oxígeno más bajo de lo habitual: repetir la medición"
    casos_spo2 = [
        ({**ev("bri", "verde", 0.9), "motivos": [motivo], "aviso_spo2": True, "accion": "Puede realizar la tarea"},
         lambda r: r.endswith(AVISO_SPO2) and "Motivos" not in r and "rango habitual" not in r),
        ({**ev("bri", "amarillo", 0.6), "motivos": ["Menos de 6 horas de sueño", motivo], "aviso_spo2": True},
         lambda r: "Motivos: menos de 6 horas de sueño." in r and r.endswith(AVISO_SPO2)),
        ({**ev("bri", "verde", 0.9), "motivos": []}, lambda r: "rango habitual" in r and AVISO_SPO2 not in r),
    ]
    for e, cumple in casos_spo2:
        r = resumen(e)
        ok = cumple(r)
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {r}")

    total = len(CASOS) + len(grupos) + len(casos_corte) + 1 + len(casos_spo2)
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
