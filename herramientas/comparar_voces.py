"""Compara las voces de Piper que hay en modelos/: dice la misma frase con cada una, una después de la otra.

  python herramientas/comparar_voces.py
  python herramientas/comparar_voces.py --frase "Hola, Bri." --velocidad 1.0

Antes de la frase, cada voz anuncia cuál es. Usa PIPER_VELOCIDAD de config.env (o --velocidad).
Para quedarse con una voz, pongan su ruta en PIPER_VOZ (config.env).
"""
import argparse
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "copiloto"))

from comun import config  # noqa: E402
from habla import cargar_piper, reproducir, sintetizar_piper, velocidad_piper  # noqa: E402

FRASE = ("Bri, tu resultado de hoy para la caminata espacial es amarillo. Recomendación: reasignar la "
         "tarea o hacerla en pareja, y descansar antes. Si no mejora, busca la ayuda de personal capacitado.")
CALIDAD = {"x_low": "muy baja", "low": "baja", "medium": "media", "high": "alta"}


def nombre_voz(ruta: Path) -> str:
    """es_MX-claude-high.onnx -> "claude, calidad alta"."""
    partes = ruta.stem.split("-")
    if len(partes) == 3:
        return f"{partes[1]}, calidad {CALIDAD.get(partes[2], partes[2])}"
    return ruta.stem


def main():
    ap = argparse.ArgumentParser(description="Compara las voces de Piper de modelos/")
    ap.add_argument("--frase", default=FRASE)
    ap.add_argument("--velocidad", type=float, default=None, help="length_scale (por defecto PIPER_VELOCIDAD)")
    args = ap.parse_args()

    velocidad = args.velocidad if args.velocidad and args.velocidad > 0 else velocidad_piper()
    actual = config.ruta("PIPER_VOZ")
    voces = []
    for ruta in sorted((RAIZ / "modelos").glob("*.onnx")):
        if Path(f"{ruta}.json").exists():
            voces.append(ruta)
        else:
            print(f"Se omite {ruta.name}: falta {ruta.name}.json")
    if not voces:
        print("No hay voces de Piper (.onnx con su .json) en modelos/.")
        return

    print(f"Velocidad: {velocidad}\n")
    for n, ruta in enumerate(voces, 1):
        marca = "  (PIPER_VOZ actual)" if actual and ruta.resolve() == actual.resolve() else ""
        print(f"Voz {n} de {len(voces)}: {ruta.name}{marca}")
        voz = cargar_piper(ruta)
        reproducir(*sintetizar_piper(voz, f"Voz {n}: {nombre_voz(ruta)}.", velocidad))
        time.sleep(0.3)
        reproducir(*sintetizar_piper(voz, args.frase, velocidad))
        time.sleep(1.0)
    print("\nListo. Para cambiar de voz, editen PIPER_VOZ en config.env.")


if __name__ == "__main__":
    main()
