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

    total = len(CASOS) + 2
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
