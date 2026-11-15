"""Historial para los paneles web: lee lo que el registrador guardó en MongoDB (colección "mensajes").

  GET /historial.json?dias=30&persona=bri   una fila por evaluación (sesión de la estación), la más vieja primero
  GET /historial.csv?dias=30&persona=bri    lo mismo en CSV, para abrirlo en una planilla
  GET /sesion.json?sesion=20261113-193005-bri   los mensajes de una sesión (para los indicadores de Resultados)

dias=0 (o sin dias) = todo. Si falta pymongo o MongoDB no responde, devuelve {"disponible": false, "motivo"}: la
estación lo muestra y sigue funcionando. Solo lee; no borra ni cambia nada. Los mensajes reproducidos
(registrador/reproducir.py) no cuentan.
"""
import csv
import io
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/

from comun import config  # noqa: E402

COLECCION = "mensajes"
TIPOS_FILA = ("evaluacion", "cuestionario", "pvt", "esp32", "vision", "control/sesion")
TIPOS_SESION = ("evaluacion", "cuestionario", "pvt", "dsst", "esp32", "vision", "voz")
CALIDAD_ESP32_MIN = 0.5  # como el coordinador: solo lecturas con dedo y calidad >= 0,5
MAX_DOCUMENTOS = 200_000
COLUMNAS_CSV = ["fecha", "persona", "sesion", "tarea", "color", "puntaje", "horas_sueno_48h", "horas_sueno", "pvt_mediana_ms",
                "pulso_lpm", "perclos", "aviso_spo2", "simulado", "provisional", "motivos"]

_cliente = None


def _coleccion():
    """La colección de MongoDB; ImportError si falta pymongo (el error de conexión aparece al usarla)."""
    global _cliente
    from pymongo import MongoClient
    if _cliente is None:
        _cliente = MongoClient(config.get("MONGO_URI", "mongodb://localhost:27017"),
                               serverSelectionTimeoutMS=1500, tz_aware=True)
    return _cliente[config.get("MONGO_DB", "apto_hoy")][COLECCION]


def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # sin NaN


def horas_48h(cu: dict):
    """Sueño de las últimas 48 h del cuestionario: el total enviado o anoche + la noche anterior."""
    total = _num(cu.get("horas_sueno_48h"))
    if total is None and _num(cu.get("horas_sueno")) is not None and _num(cu.get("horas_sueno_previa")) is not None:
        total = _num(cu.get("horas_sueno")) + _num(cu.get("horas_sueno_previa"))
    return total


def _ms(fecha) -> int:
    if isinstance(fecha, datetime):
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)  # el registrador guarda en UTC
        return int(fecha.timestamp() * 1000)
    return 0


def _no_disponible(e: Exception) -> dict:
    if isinstance(e, ImportError):
        return {"disponible": False, "motivo": "Falta pymongo en el Python de servidor.py (pip install pymongo)."}
    return {"disponible": False, "motivo": f"MongoDB no responde ({type(e).__name__}). Revisen que mongo_local.py "
                                           "y el registrador estén abiertos."}


def filas_de(docs) -> list[dict]:
    """Documentos del registrador -> una fila por sesión con evaluación, ordenadas por fecha.

    Cada documento: {tipo, persona, recibido, datos}. Si el coordinador recalculó, vale la última evaluación;
    el pulso es la mediana de las lecturas del ESP32 con dedo y calidad >= 0,5."""
    sesiones: dict[str, dict] = {}
    for d in sorted(docs, key=lambda x: _ms(x.get("recibido"))):
        datos = d.get("datos") or {}
        sid = datos.get("sesion")
        if not sid:
            continue
        s = sesiones.setdefault(sid, {"esp32": []})
        tipo = d.get("tipo")
        if tipo == "esp32":
            s["esp32"].append(datos)
        else:
            s[tipo] = (d, datos)
    filas = []
    for sid, s in sesiones.items():
        if "evaluacion" not in s:
            continue
        doc, ev = s["evaluacion"]
        cu = s.get("cuestionario", (None, {}))[1]
        pv = s.get("pvt", (None, {}))[1]
        vi = s.get("vision", (None, {}))[1]
        se = s.get("control/sesion", (None, {}))[1]
        validas = [m for m in s["esp32"] if m.get("dedo") is True and (_num(m.get("calidad")) or 0) >= CALIDAD_ESP32_MIN]
        pulsos = [v for v in (_num(m.get("pulso_lpm")) for m in validas) if v is not None]
        perclos = _num(vi.get("perclos"))
        filas.append({
            "id": sid, "persona": doc.get("persona") or ev.get("persona"), "fecha": _ms(doc.get("recibido")),
            "color": ev.get("color"), "puntaje": _num(ev.get("puntaje")), "motivos": ev.get("motivos") or [],
            "accion": ev.get("accion"), "tarea": ev.get("tarea") or se.get("tarea") or "",
            "horas_sueno_48h": horas_48h(cu), "horas_sueno": _num(cu.get("horas_sueno")),
            "pvt_mediana": _num(pv.get("rt_mediana_ms")),
            "pulso_lpm": round(statistics.median(pulsos), 1) if pulsos else None,
            "perclos": perclos / 100 if perclos is not None and perclos > 1 else perclos,
            "aviso_spo2": bool(ev.get("aviso_spo2")), "simulado": bool(ev.get("simulado")),
            "provisional": bool(ev.get("provisional")),
        })
    filas.sort(key=lambda f: f["fecha"])
    return filas


def historial(dias: int = 0, persona: str = "") -> dict:
    q = {"tipo": {"$in": list(TIPOS_FILA)}, "reproducido": False, "datos.sesion": {"$exists": True}}
    if dias > 0:
        q["recibido"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=dias)}
    if persona:
        q["persona"] = persona.lower()
    try:
        docs = list(_coleccion().find(q, {"_id": 0, "tipo": 1, "persona": 1, "recibido": 1, "datos": 1})
                    .sort("recibido", 1).limit(MAX_DOCUMENTOS))
    except Exception as e:  # sin pymongo o sin MongoDB: la estación lo muestra
        return _no_disponible(e)
    return {"disponible": True, "filas": filas_de(docs)}


def sesion(sid: str) -> dict:
    if not sid:
        return {"disponible": False, "motivo": "Falta el parámetro sesion."}
    q = {"datos.sesion": sid, "reproducido": False, "tipo": {"$in": list(TIPOS_SESION)}}
    try:
        docs = list(_coleccion().find(q, {"_id": 0, "tipo": 1, "persona": 1, "datos": 1}).sort("recibido", 1).limit(5000))
    except Exception as e:
        return _no_disponible(e)
    return {"disponible": True, "mensajes": [{"tipo": d.get("tipo"), "persona": d.get("persona"), "datos": d.get("datos") or {}}
                                             for d in docs]}


def a_csv(filas: list[dict]) -> str:
    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\r\n")
    w.writerow(COLUMNAS_CSV)
    for f in filas:
        fecha = datetime.fromtimestamp(f["fecha"] / 1000).strftime("%Y-%m-%d %H:%M:%S") if f["fecha"] else ""
        valores = {**f, "fecha": fecha, "sesion": f["id"], "pvt_mediana_ms": f["pvt_mediana"], "motivos": " | ".join(f["motivos"])}
        w.writerow(["" if valores.get(c) is None else str(valores.get(c)).lower() if isinstance(valores.get(c), bool)
                    else valores.get(c) for c in COLUMNAS_CSV])
    return salida.getvalue()
