"""Prueba simple del registrador sin MongoDB ni MQTT (una colección falsa que se puede «caer»).

  python registrador/pruebas_registrador.py

Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from almacen import a_linea, de_linea, documento, fecha_local, persona_y_tipo  # noqa: E402
from pymongo.errors import BulkWriteError, ServerSelectionTimeoutError  # noqa: E402
from registrador import Registrador  # noqa: E402
from reproducir import se_reproduce  # noqa: E402


class ColeccionFalsa:
    """Guarda por _id; si caida=True, falla como un MongoDB que no responde."""

    def __init__(self):
        self.docs = {}
        self.caida = False

    def _id(self, doc):
        from bson import ObjectId
        doc.setdefault("_id", ObjectId())
        return doc["_id"]

    def insert_one(self, doc):
        self._id(doc)  # pymongo le pone _id antes de enviarlo
        if self.caida:
            raise ServerSelectionTimeoutError("sin servidor")
        self.docs[doc["_id"]] = doc

    def insert_many(self, docs, ordered=True):
        if self.caida:
            raise ServerSelectionTimeoutError("sin servidor")
        errores = []
        for i, d in enumerate(docs):
            if self._id(d) in self.docs:
                errores.append({"index": i, "code": 11000, "errmsg": "duplicate key"})
            else:
                self.docs[d["_id"]] = d
        if errores:
            raise BulkWriteError({"writeErrors": errores})

    def ping(self):
        if self.caida:
            raise ServerSelectionTimeoutError("sin servidor")


fallas = 0
total = 0


def revisar(ok, texto, detalle=""):
    global fallas, total
    total += 1
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  {texto}")
    if not ok and detalle:
        print(f"       {detalle}")


def main() -> int:
    print("--- forma de los documentos ---")
    casos = [("apto/bri/pvt", {}, ("bri", "pvt")),
             ("apto/control/sesion", {"persona": "sebas"}, ("sebas", "control/sesion")),
             ("apto/control/modulos/voz", {"activo": True}, (None, "control/modulos"))]
    for tema, datos, esperado in casos:
        r = persona_y_tipo(tema, datos)
        revisar(r == esperado, f"{tema} -> persona {r[0]!r}, tipo {r[1]!r}", f"esperado {esperado}")
    d = documento("apto/bri/evaluacion", {"color": "rojo", "simulado": True, "reproducido": True})
    revisar(d["simulado"] and d["reproducido"] and d["datos"]["color"] == "rojo" and d["recibido"].tzinfo,
            "documento: simulado, reproducido, datos originales y fecha con zona")
    vuelta = de_linea(a_linea({**d, "_id": None}))
    revisar(vuelta["recibido"] == d["recibido"] and vuelta["datos"] == d["datos"] and vuelta["_id"] is not None,
            "una línea de pendientes vuelve igual (fecha, datos y _id)")
    f = fecha_local("2026-11-13 20:47")
    revisar(f.tzinfo is not None and (f.hour, f.minute) == (20, 47), f"fecha_local con la zona de esta PC: {f.isoformat()}")

    print("\n--- MongoDB se cae y vuelve: no se pierde nada ---")
    col = ColeccionFalsa()
    with tempfile.TemporaryDirectory() as carpeta:
        pendientes = Path(carpeta) / "pendientes_mongo.jsonl"
        reg = Registrador(col, col.ping, pendientes)
        reg.guardar("apto/bri/pvt", {"lapsos": 1})
        revisar(len(col.docs) == 1 and not pendientes.exists(), "con Mongo bien: va directo a la colección")
        reg.guardar("apto/bri/evaluacion", {"color": "verde"}, retenido=True)
        revisar(len(col.docs) == 1, "un mensaje retenido (al conectarse) no se guarda otra vez")
        col.caida = True
        for i in range(3):
            reg.guardar("apto/bri/esp32", {"pulso_lpm": 70 + i})
        lineas = pendientes.read_text(encoding="utf-8").splitlines() if pendientes.exists() else []
        revisar(reg.caido and len(lineas) == 3 and len(col.docs) == 1, f"con Mongo caído: {len(lineas)} mensajes al archivo")
        revisar(reg.subir_pendientes() == 0 and pendientes.exists(), "mientras sigue caído, el archivo se conserva")
        col.caida = False
        primero = de_linea(lineas[0])
        col.docs[primero["_id"]] = primero  # como si uno hubiera alcanzado a guardarse antes de la caída
        subidos = reg.subir_pendientes()
        pulsos = sorted(x["datos"]["pulso_lpm"] for x in col.docs.values() if x["tipo"] == "esp32")
        revisar(subidos == 3 and not pendientes.exists() and not reg.caido and pulsos == [70, 71, 72],
                f"Mongo vuelve: subió {subidos}, sin duplicados {pulsos}, archivo borrado")
        reg.guardar("apto/bri/pvt", {"lapsos": 0})
        revisar(len(col.docs) == 5, "después vuelve a guardar directo en la colección")

    print("\n--- qué se reproduce ---")
    tipos = {"pvt": True, "evaluacion": True, "copiloto": True, "control/sesion": True,
             "control/orden_voz": False, "control/pregunta": False, "control/modulos": False}
    malos = {t: e for t, e in tipos.items() if se_reproduce(t) != e}
    revisar(not malos, "datos, evaluación, copiloto y sesión sí; órdenes, preguntas y módulos no", f"fallan: {malos}")

    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
