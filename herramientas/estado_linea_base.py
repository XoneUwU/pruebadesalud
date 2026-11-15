"""Muestra la línea base que tiene cada persona y lo que le falta para que el sistema pueda comparar.

  python herramientas/estado_linea_base.py
  python herramientas/estado_linea_base.py --persona bri

Lee los dos lugares donde se guarda la línea base (solo lee, no cambia nada):
  datos/coordinador/linea_base.jsonl   lo de la estación: reacción, símbolos, cuestionario, cámara y sensor.
                                       El coordinador promedia TODAS las de la persona (con 1 ya compara).
  datos/voz/historial.jsonl            las voces: hacen falta 3 de la frase estándar (voz_fatiga.MIN_LINEA_BASE).
Avisa si una línea base se tomó con sueño (Karolinska 6 o más, o menos de 6 h de sueño), porque el sistema la
toma como el estado normal de la persona.
"""
import argparse
import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ARCHIVO_COORDINADOR = RAIZ / "datos" / "coordinador" / "linea_base.jsonl"
ARCHIVO_VOZ = RAIZ / "datos" / "voz" / "historial.jsonl"
PERSONAS = ("bri", "danilo", "sebas", "eric", "adrian")
ESTACION = {"pvt": "reacción", "dsst": "símbolos", "cuestionario": "cuestionario", "vision": "cámara",
            "esp32": "sensor"}
VOCES_NECESARIAS = 3  # igual que MIN_LINEA_BASE en voz/voz_fatiga.py


def leer_jsonl(archivo: Path) -> list[dict]:
    if not archivo.exists():
        return []
    filas = []
    for linea in archivo.read_text(encoding="utf-8").splitlines():
        try:
            filas.append(json.loads(linea))
        except json.JSONDecodeError:
            continue
    return filas


def avisos_estacion(tipo: str, sesion: str, d: dict) -> list[str]:
    """Problemas de una medición de línea base que la hacen inútil o engañosa."""
    r = []
    if tipo == "cuestionario":
        kss, horas = d.get("kss"), d.get("horas_sueno")
        if (kss is not None and kss >= 6) or (horas is not None and horas < 6):
            r.append(f"se tomó con sueño (Karolinska {kss}, {horas} h de sueño) en la sesión {sesion}")
    elif tipo == "vision":
        cara = d.get("cara_detectada_pct")
        if cara is not None and cara < 50:
            r.append(f"la cámara vio poco la cara ({cara} %) en la sesión {sesion}: esa medición no cuenta")
        if d.get("lentes"):
            r.append(f"cámara con lentes en la sesión {sesion}: los ojos no cuentan")
    elif tipo == "esp32" and d.get("pulso_lpm") is None:
        r.append(f"el sensor no dio pulso válido en la sesión {sesion}")
    return r


def sirve(tipo: str, d: dict) -> bool:
    """Si la medición le sirve al coordinador: un sensor sin pulso (se omitió o sin dedo) o una cámara que vio
    poco la cara quedan guardados, pero no cuentan."""
    if tipo == "esp32":
        return d.get("pulso_lpm") is not None
    if tipo == "vision":
        cara = d.get("cara_detectada_pct")
        return cara is None or cara >= 50
    return True


def estado(persona: str, coordinador: list[dict], voces: list[dict]) -> list[str]:
    filas = [f for f in coordinador if f.get("persona") == persona]
    cuenta = {t: sum(1 for f in filas if f.get("tipo") == t and sirve(t, f.get("datos") or {})) for t in ESTACION}
    n_voz = sum(1 for v in voces if v.get("persona") == persona and v.get("linea_base") and v.get("voz_detectada")
                and (v.get("frase_id") or "estandar") == "estandar")
    falta = [ESTACION[t] for t, n in cuenta.items() if n == 0]
    if n_voz < VOCES_NECESARIAS:
        k = VOCES_NECESARIAS - n_voz
        falta.append(f"{k} {'voz estándar' if k == 1 else 'voces estándar'}")
    lineas = [f"{persona}: " + ("completa" if not falta else "le falta " + ", ".join(falta))]
    lineas.append("  estación: " + " · ".join(f"{ESTACION[t]} {n}" for t, n in cuenta.items()))
    lineas.append(f"  voces estándar: {n_voz} de {VOCES_NECESARIAS}")
    n_musculo = sum(1 for f in filas if f.get("tipo") == "esp32" and (f.get("datos") or {}).get("musculo_relacion")
                    is not None and not (f.get("datos") or {}).get("musculo_simulado"))
    lineas.append(f"  músculo (AD8232, prototipo; no suma al semáforo ni hace falta): {n_musculo}")
    for f in filas:
        for aviso in avisos_estacion(f.get("tipo"), f.get("sesion"), f.get("datos") or {}):
            lineas.append(f"  OJO: {aviso}")
    return lineas


def main():
    ap = argparse.ArgumentParser(description="Línea base de cada persona y lo que le falta.")
    ap.add_argument("--persona", help="solo esta persona (en minúsculas)")
    args = ap.parse_args()
    coordinador, voces = leer_jsonl(ARCHIVO_COORDINADOR), leer_jsonl(ARCHIVO_VOZ)
    if args.persona:
        personas = [args.persona.strip().lower()]
    else:  # las cinco, más cualquier otra que ya tenga línea base
        otras = {f.get("persona") for f in coordinador} | {v.get("persona") for v in voces if v.get("linea_base")}
        personas = list(PERSONAS) + sorted(p for p in otras - set(PERSONAS) if p)
    for p in personas:
        print("\n".join(estado(p, coordinador, voces)))
        print()


if __name__ == "__main__":
    main()
