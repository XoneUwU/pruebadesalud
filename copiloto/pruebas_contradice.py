"""Prueba simple del filtro contradice() del copiloto (no necesita MQTT ni Ollama).

  python copiloto/pruebas_contradice.py

Muestra OK o FALLA por cada frase y termina con código 1 si alguna falla.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from copiloto import contradice  # noqa: E402

AMARILLO = {"persona": "xone", "color": "amarillo", "tarea": "caminata espacial"}
VERDE = {**AMARILLO, "color": "verde"}

# (frase, evaluación, ¿debe marcarla como contradicción?)
CASOS = [
    # --- casos pedidos
    ("Puedes hacer una siesta corta de 20 minutos", AMARILLO, False),
    ("Puedes hacer una respiración lenta", AMARILLO, False),
    ("Puedes realizar la evaluación de nuevo", AMARILLO, False),
    ("Sí, puedes hacer la caminata espacial.", AMARILLO, True),
    ("Estás lista para la caminata.", AMARILLO, True),
    ("Claro, puedes salir a la caminata sin problema.", AMARILLO, True),
    ("No puedes hacer la caminata hasta descansar.", AMARILLO, False),
    # --- casos extra: reglas de apoyo del filtro
    ("Puedes hacer una siesta corta antes de la caminata.", AMARILLO, False),  # consejo, aunque nombre la tarea
    ("Antes de salir a la caminata, revisa el traje.", AMARILLO, False),       # preparación, no permiso
    ("Deja la caminata para más adelante.", AMARILLO, False),                  # "más adelante" no es "adelante"
    ("Aún no estás lista para la caminata.", AMARILLO, False),                 # negación
    ("Descansa primero. Luego puedes ir a la caminata.", AMARILLO, True),      # se revisa frase por frase
    ("La caminata la hará Eric. Tú puedes ayudar desde la nave.", AMARILLO, False),  # permiso y tarea en frases distintas
    ("Sí, puedes hacer la caminata espacial.", VERDE, False),                  # en verde no hay contradicción
]


def main() -> int:
    fallas = 0
    for frase, ev, esperado in CASOS:
        obtenido = contradice(frase, ev)
        ok = obtenido == esperado
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  esperado={'sí' if esperado else 'no'}  "
              f"obtenido={'sí' if obtenido else 'no'}  [{ev['color']}]  {frase}")
    print(f"\n{len(CASOS) - fallas} de {len(CASOS)} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
