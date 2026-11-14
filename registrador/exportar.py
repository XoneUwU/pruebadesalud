"""Exporta los mensajes guardados en MongoDB a CSV, un archivo por tipo (para los gráficos de validación).

  python registrador/exportar.py                              todos los tipos, a datos/exportes/
  python registrador/exportar.py --tipo pvt --tipo dsst       solo esos tipos
  python registrador/exportar.py --persona bri --desde "2026-11-13 20:00" --hasta "2026-11-13 21:00"
  python registrador/exportar.py --solo-reales                sin datos simulados ni reproducidos
  python registrador/exportar.py --excel                      separador ";" y coma decimal (Excel en español)

Columnas: recibido (hora de esta PC), persona, tema, simulado, reproducido y un campo por cada dato del
mensaje. Las listas se unen con " | " y los objetos quedan como JSON.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from almacen import conectar, fecha_local, hora_local  # noqa: E402

from comun import config  # noqa: E402

CARPETA = config.RAIZ / "datos" / "exportes"
FIJAS = ["recibido", "persona", "tema", "simulado", "reproducido"]


def valor_csv(v, excel: bool) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and excel:
        return repr(v).replace(".", ",")
    if isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v):
        return " | ".join(str(x) for x in v)
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return str(v)


def filtro(args) -> dict:
    q = {}
    if args.persona:
        q["persona"] = args.persona.lower()
    if args.desde or args.hasta:
        q["recibido"] = {}
        if args.desde:
            q["recibido"]["$gte"] = fecha_local(args.desde)
        if args.hasta:
            q["recibido"]["$lte"] = fecha_local(args.hasta)
    if args.solo_reales:
        q["simulado"] = False
        q["reproducido"] = False
    return q


def main():
    ap = argparse.ArgumentParser(description="Exporta los mensajes de MongoDB a CSV por tipo")
    ap.add_argument("--tipo", action="append", help="tipo a exportar (se puede repetir); por defecto, todos")
    ap.add_argument("--persona")
    ap.add_argument("--desde", help='"2026-11-13 20:00" (hora de esta PC)')
    ap.add_argument("--hasta")
    ap.add_argument("--solo-reales", action="store_true", help="sin simulados ni reproducidos")
    ap.add_argument("--excel", action="store_true", help='separador ";" y coma decimal')
    ap.add_argument("--salida", type=Path, default=CARPETA)
    args = ap.parse_args()

    cliente, col = conectar(timeout_ms=3000)
    q = filtro(args)
    try:
        tipos = args.tipo or sorted(col.distinct("tipo", q))
    except Exception as e:
        print(f"MongoDB no responde ({type(e).__name__}). ¿Está abierto registrador\\mongo_local.py?")
        return
    if not tipos:
        print("No hay mensajes con ese filtro.")
        return
    args.salida.mkdir(parents=True, exist_ok=True)
    for tipo in tipos:
        docs = list(col.find({**q, "tipo": tipo}).sort("recibido", 1))
        if not docs:
            print(f"{tipo:22} sin mensajes")
            continue
        campos = []  # los del mensaje, en el orden en que aparecen
        for d in docs:
            campos += [k for k in d.get("datos", {}) if k not in campos and k not in FIJAS]
        archivo = args.salida / f"{tipo.replace('/', '_')}.csv"
        with open(archivo, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig: Excel lee bien las tildes
            w = csv.writer(f, delimiter=";" if args.excel else ",")
            w.writerow(FIJAS + campos)
            for d in docs:
                datos = d.get("datos", {})
                fila = [hora_local(d["recibido"]), d.get("persona"), d.get("tema"), d.get("simulado"), d.get("reproducido")]
                w.writerow([valor_csv(v, args.excel) for v in fila] + [valor_csv(datos.get(c), args.excel) for c in campos])
        print(f"{tipo:22} {len(docs):5} filas -> {archivo}")
    cliente.close()


if __name__ == "__main__":
    main()
