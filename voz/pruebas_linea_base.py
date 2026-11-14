"""Prueba simple de la comparación con la línea base de la voz (datos inventados; no necesita micrófono ni MQTT).

  python voz/pruebas_linea_base.py

Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voz_fatiga import comparar_con_linea_base, leer_linea_base  # noqa: E402


def medicion(pausas, habla, intensidad, f0_desv, jitter, shimmer, hnr, **extra) -> dict:
    return {"persona": "bri", "linea_base": False, "voz_detectada": True, "num_pausas": pausas,
            "tiempo_habla_s": habla, "intensidad_media_db": intensidad, "f0_desv_hz": f0_desv,
            "jitter_local": jitter, "shimmer_local": shimmer, "hnr_db": hnr, **extra}


# Línea base inventada: 3 mediciones con la persona descansada.
BASE = [
    medicion(1, 8.0, 76.0, 36.0, 0.021, 0.100, 11.5, linea_base=True),
    medicion(2, 8.3, 76.8, 38.0, 0.022, 0.098, 11.0, linea_base=True),
    medicion(1, 8.1, 77.4, 37.0, 0.020, 0.104, 11.8, linea_base=True),
]
CANSADA = medicion(4, 9.2, 74.5, 30.0, 0.024, 0.108, 10.2)  # más pausas, lectura lenta, voz baja, tono plano
NORMAL = medicion(1, 8.2, 76.5, 37.5, 0.021, 0.101, 11.3)   # parecida a la línea base
ENERGIA = medicion(0, 7.6, 79.0, 42.0, 0.020, 0.099, 12.2)  # extra: menos pausas, más rápida, más fuerte

# (nombre, medición, línea base, estado esperado, motivos esperados)
CASOS = [
    ("cansada", CANSADA, BASE, "más cansada que su línea base",
     ["Lectura más lenta de lo habitual", "Más pausas de lo habitual"]),
    ("normal", NORMAL, BASE, "normal", []),
    # --- casos extra
    ("con energía", ENERGIA, BASE, "con más energía que su línea base",
     ["Lectura más rápida de lo habitual", "Tono más variado de lo habitual"]),
    ("solo 2 de línea base", CANSADA, BASE[:2], "sin línea base", []),
    ("sin voz", {**CANSADA, "voz_detectada": False}, BASE, "sin voz detectada", []),
]


def main() -> int:
    fallas = 0
    for nombre, med, base, estado, motivos in CASOS:
        r = comparar_con_linea_base(med, base)
        ok = r["estado_voz"] == estado and r["motivos_voz"] == motivos
        if estado == "más cansada que su línea base":
            ok = ok and r["indice_cansancio"] > 1
        elif estado == "normal":
            ok = ok and -1 <= r["indice_cansancio"] <= 1
        elif estado.startswith("con más energía"):
            ok = ok and r["indice_cansancio"] < -1
        else:
            ok = ok and r["indice_cansancio"] is None
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  {nombre}: estado={r['estado_voz']!r}  "
              f"índice={r['indice_cansancio']}  motivos={r['motivos_voz']}")
        if not ok:
            print(f"       esperado: estado={estado!r}  motivos={motivos}  z={r['z_rasgos']}")

    # leer_linea_base: solo cuenta las mediciones de la persona, marcadas con linea_base y con voz.
    with tempfile.TemporaryDirectory() as carpeta:
        historial = Path(carpeta) / "historial.jsonl"
        filas = BASE + [
            NORMAL,                                               # no es línea base
            {**BASE[0], "voz_detectada": False},                  # línea base sin voz
            {**BASE[0], "persona": "erick"},                      # otra persona
        ]
        historial.write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in filas) + "línea rota\n",
                             encoding="utf-8")
        n = len(leer_linea_base("bri", historial))
        ok = n == 3
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  leer_linea_base: {n} mediciones de bri (esperadas 3)")

        # Cada frase tiene su propia línea base: el trabalenguas no se mezcla con la estándar.
        mas = [{**BASE[0], "frase_id": "trabalenguas"}, {**BASE[1], "frase_id": "trabalenguas"},
               {**BASE[2], "frase_id": "estandar"}]
        with open(historial, "a", encoding="utf-8") as f:
            f.write("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in mas))
        estandar = len(leer_linea_base("bri", historial))
        trabalenguas = len(leer_linea_base("bri", historial, frase_id="trabalenguas"))
        ok = estandar == 4 and trabalenguas == 2
        fallas += not ok
        print(f"{'OK   ' if ok else 'FALLA'}  línea base por frase: estándar {estandar} (3 viejas sin frase_id + 1), "
              f"trabalenguas {trabalenguas} (esperadas 4 y 2)")

    total = len(CASOS) + 2
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
