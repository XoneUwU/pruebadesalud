"""Lo común del registrador: conexión a MongoDB, forma de cada documento, archivo de pendientes y fechas.

Documento de la colección "mensajes" (base MONGO_DB):
  {recibido (fecha, UTC), tema, persona, tipo, simulado, reproducido, datos: <el JSON original>}
  apto/bri/pvt            -> persona "bri",   tipo "pvt"
  apto/control/sesion     -> persona de datos (si la trae), tipo "control/sesion"
  apto/control/modulos/voz-> persona None,    tipo "control/modulos"
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/

from comun import config  # noqa: E402

COLECCION = "mensajes"
PENDIENTES = config.RAIZ / "datos" / "pendientes_mongo.jsonl"


def conectar(timeout_ms: int = 2000):
    """(cliente, colección). No falla si Mongo no está: el error aparece al usarla."""
    from pymongo import MongoClient
    cliente = MongoClient(config.get("MONGO_URI", "mongodb://localhost:27017"),
                          serverSelectionTimeoutMS=timeout_ms, tz_aware=True)
    return cliente, cliente[config.get("MONGO_DB", "apto_hoy")][COLECCION]


def crear_indices(col):
    col.create_index([("persona", 1), ("tipo", 1), ("recibido", 1)], name="persona_tipo_recibido")
    col.create_index("tipo", name="tipo")


def persona_y_tipo(tema: str, datos: dict) -> tuple[str | None, str]:
    partes = tema.split("/")
    if len(partes) >= 3 and partes[1] == "control":
        return datos.get("persona") or None, f"control/{partes[2]}"
    if len(partes) >= 3:
        return partes[1], "/".join(partes[2:])
    return datos.get("persona") or None, tema


def documento(tema: str, datos, recibido: datetime | None = None) -> dict:
    if not isinstance(datos, dict):
        datos = {"valor": datos}
    persona, tipo = persona_y_tipo(tema, datos)
    return {
        "recibido": recibido or datetime.now(timezone.utc), "tema": tema, "persona": persona, "tipo": tipo,
        "simulado": bool(datos.get("simulado")), "reproducido": bool(datos.get("reproducido")), "datos": datos,
    }


def a_linea(doc: dict) -> str:
    """Documento -> línea de pendientes_mongo.jsonl (con su _id, para no duplicar al reintentar)."""
    from bson import ObjectId
    fila = dict(doc)
    fila["_id"] = str(fila.get("_id") or ObjectId())
    fila["recibido"] = fila["recibido"].isoformat()
    return json.dumps(fila, ensure_ascii=False)


def de_linea(linea: str) -> dict:
    from bson import ObjectId
    doc = json.loads(linea)
    doc["_id"] = ObjectId(doc["_id"])
    doc["recibido"] = datetime.fromisoformat(doc["recibido"])
    return doc


def fecha_local(texto: str) -> datetime:
    """"2026-11-13 20:47" o "2026-11-13T20:47:30" (hora de esta PC) -> fecha con zona horaria."""
    f = datetime.fromisoformat(texto.strip())
    return f if f.tzinfo else f.astimezone()  # sin zona: la de esta PC


def hora_local(fecha: datetime) -> str:
    return fecha.astimezone().strftime("%Y-%m-%d %H:%M:%S")
