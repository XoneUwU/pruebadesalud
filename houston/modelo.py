"""Modelo de Houston: lee la base de Tierra (HOUSTON_MONGO_DB, colección "mensajes").

La llena receptor.py, suscrito a Mosquitto (apto/#). No es una copia exacta de la base de la nave: solo trae los tipos
de TIPOS (sin órdenes ni estados de los módulos) y cada documento lleva además `llego_tierra` (recibido + retraso de la
comunicación). Solo se muestra lo que ya llegó: `llego_tierra` <= ahora. Houston solo lee: no publica por MQTT.

Las funciones que arman las respuestas (filas_de, armar_tablero, a_csv) no tocan MongoDB: se prueban sin él.
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
COLECCION_ENLACE = "enlace"
# Lo que baja de la nave a Tierra (lo usa también enlace.py).
TIPOS = ("evaluacion", "cuestionario", "pvt", "dsst", "esp32", "vision", "voz", "copiloto", "control/sesion")
TIPOS_FILA = ("evaluacion", "cuestionario", "pvt", "dsst", "esp32", "vision", "voz", "control/sesion")
CALIDAD_ESP32_MIN = 0.5    # como el coordinador: solo lecturas con dedo y calidad >= 0,5
SIN_SENAL_S = 30           # si el enlace no da señales en este tiempo, el tablero dice «sin señal»
MAX_DOCUMENTOS = 200_000
COLUMNAS_CSV = ["fecha_nave", "llego_tierra", "persona", "sesion", "tarea", "color", "puntaje", "kss", "horas_sueno",
                "pvt_mediana_ms", "pvt_lapsos", "dsst_por_minuto", "pulso_lpm", "spo2_min", "perclos", "estado_voz",
                "aviso_spo2", "simulado", "provisional", "motivos"]

_cliente = None


def base():
    """La base de la réplica; ImportError si falta pymongo (el error de conexión aparece al usarla)."""
    global _cliente
    from pymongo import MongoClient
    if _cliente is None:
        _cliente = MongoClient(config.get("HOUSTON_MONGO_URI", "mongodb://localhost:27017"),
                               serverSelectionTimeoutMS=1500, tz_aware=True)
    return _cliente[config.get("HOUSTON_MONGO_DB", "houston")]


def tripulacion() -> list[str]:
    return [p.strip().lower() for p in config.get("TRIPULACION").split(",") if p.strip()]


def retraso_s() -> int:
    return config.get_int("HOUSTON_RETRASO_S", config.get_int("RETRASO_TIERRA_S", 20))


# ---------------------------------------------------------------- utilidades

def _num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v else None  # sin NaN


def _ms(fecha) -> int | None:
    if isinstance(fecha, datetime):
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)  # el registrador guarda en UTC
        return int(fecha.timestamp() * 1000)
    return None


def _no_disponible(e: Exception) -> dict:
    if isinstance(e, ImportError):
        return {"disponible": False, "motivo": "Falta pymongo en el Python de houston/servidor.py (pip install pymongo)."}
    return {"disponible": False, "motivo": f"La base de Houston no responde ({type(e).__name__}). Revisen que su "
                                           "MongoDB esté abierto (docker compose up en houston/)."}


# ---------------------------------------------------------------- armado (sin MongoDB)

def filas_de(docs) -> list[dict]:
    """Documentos de la réplica -> una fila por sesión con evaluación, la más vieja primero.

    Cada documento: {tipo, persona, recibido, llego_tierra, datos}. Si el coordinador recalculó, vale la última
    evaluación; el pulso es la mediana de las lecturas del ESP32 con dedo y calidad >= 0,5."""
    sesiones: dict[str, dict] = {}
    for d in sorted(docs, key=lambda x: _ms(x.get("recibido")) or 0):
        datos = d.get("datos") or {}
        sid = datos.get("sesion")
        if not sid:
            continue
        s = sesiones.setdefault(sid, {"esp32": []})
        tipo = d.get("tipo")
        if tipo == "esp32":
            s["esp32"].append(datos)
        elif tipo in TIPOS_FILA:
            s[tipo] = (d, datos)
    filas = []
    for sid, s in sesiones.items():
        if "evaluacion" not in s:
            continue
        doc, ev = s["evaluacion"]
        cu = s.get("cuestionario", (None, {}))[1]
        pv = s.get("pvt", (None, {}))[1]
        ds = s.get("dsst", (None, {}))[1]
        vi = s.get("vision", (None, {}))[1]
        vo = s.get("voz", (None, {}))[1]
        se = s.get("control/sesion", (None, {}))[1]
        validas = [m for m in s["esp32"] if m.get("dedo") is True and (_num(m.get("calidad")) or 0) >= CALIDAD_ESP32_MIN]
        pulsos = [v for v in (_num(m.get("pulso_lpm")) for m in validas) if v is not None]
        spo2 = [v for v in (_num(m.get("spo2")) for m in validas) if v is not None]
        perclos = _num(vi.get("perclos"))
        filas.append({
            "id": sid, "persona": doc.get("persona") or ev.get("persona"),
            "fecha": _ms(doc.get("recibido")), "llego": _ms(doc.get("llego_tierra")),
            "color": ev.get("color"), "puntaje": _num(ev.get("puntaje")), "motivos": ev.get("motivos") or [],
            "accion": ev.get("accion"), "tarea": ev.get("tarea") or se.get("tarea") or "",
            "kss": _num(cu.get("kss")), "horas_sueno": _num(cu.get("horas_sueno")),
            "pvt_mediana": _num(pv.get("rt_mediana_ms")), "pvt_lapsos": _num(pv.get("lapsos")),
            "dsst_por_minuto": _num(ds.get("por_minuto")),
            "pulso_lpm": round(statistics.median(pulsos), 1) if pulsos else None,
            "spo2_min": min(spo2) if spo2 else None,
            "perclos": perclos / 100 if perclos is not None and perclos > 1 else perclos,
            "estado_voz": vo.get("estado_voz"),
            "aviso_spo2": bool(ev.get("aviso_spo2")), "simulado": bool(ev.get("simulado")),
            "provisional": bool(ev.get("provisional")),
        })
    filas.sort(key=lambda f: f["fecha"] or 0)
    return filas


def estado_enlace(estado: dict | None, ahora_ms: int, en_camino: int = 0, ultimo_dato: int | None = None) -> dict:
    """El documento de receptor.py -> lo que muestra el tablero.

    Hay señal si el receptor escribió hace menos de SIN_SENAL_S y está conectado a Mosquitto."""
    estado = estado or {}
    actualizado = _ms(estado.get("actualizado"))
    vivo = actualizado is not None and ahora_ms - actualizado <= SIN_SENAL_S * 1000
    error = estado.get("error") or ""
    if actualizado is not None and not vivo:
        error = "El receptor de Houston no responde"
    return {
        "retraso_s": estado.get("retraso_s", retraso_s()),
        "actualizado": actualizado,
        "ultimo_dato_nave": ultimo_dato,
        "copiados": int(estado.get("guardados") or 0),
        "en_camino": en_camino,
        "con_senal": vivo and bool(estado.get("conectado")),
        "error": error,
    }


PASOS_VIVO = ("esp32", "vision", "voz", "pvt", "dsst", "cuestionario")
VIVO_MIN = 30          # una sesión iniciada hace más de esto ya no está «en vivo»
VIVO_RESULTADO_S = 300  # con su evaluación ya en Tierra, sigue en «En vivo» estos segundos y después se va
DATO_VIGENTE_S = 15     # una lectura del ESP32 más vieja que esto ya no es «en vivo»
SERIE_PULSO = 90        # lecturas de pulso para la curva


def en_vivo(docs, ahora_ms: int) -> list[dict]:
    """Las sesiones en curso (iniciadas hace menos de VIVO_MIN), la más nueva por persona: qué pasos ya llegaron, la
    última lectura del ESP32, la curva del pulso y la evaluación si ya llegó. `docs`: lo que ya está en Tierra."""
    por_sesion: dict[str, list] = {}
    inicios: dict[str, dict] = {}   # persona -> doc de control/sesion más nuevo
    for d in sorted(docs, key=lambda x: _ms(x.get("recibido")) or 0):
        datos = d.get("datos") or {}
        sid = datos.get("sesion")
        if not sid:
            continue
        por_sesion.setdefault(sid, []).append(d)
        if d.get("tipo") == "control/sesion":
            persona = datos.get("persona") or d.get("persona")
            if persona:
                inicios[persona] = d
    vivas = []
    for persona, inicio in inicios.items():
        t0 = _ms(inicio.get("recibido")) or 0
        if ahora_ms - t0 > VIVO_MIN * 60_000:
            continue
        sid = inicio["datos"]["sesion"]
        sesion_docs = por_sesion.get(sid, [])
        evs = [d for d in sesion_docs if d.get("tipo") == "evaluacion"]
        ev = evs[-1] if evs else None
        if ev and ahora_ms - (_ms(ev.get("llego_tierra")) or _ms(ev.get("recibido")) or 0) > VIVO_RESULTADO_S * 1000:
            continue
        esp = [d for d in sesion_docs if d.get("tipo") == "esp32"]
        ult = esp[-1] if esp else None
        ult_d = (ult or {}).get("datos") or {}
        serie = [[_ms(d.get("recibido")), _num((d.get("datos") or {}).get("pulso_lpm"))] for d in esp[-SERIE_PULSO:]]
        ultimo_dato = max((_ms(d.get("recibido")) or 0 for d in sesion_docs), default=t0)
        ev_d = (ev or {}).get("datos") or {}
        vivas.append({
            "persona": persona, "sesion": sid, "tarea": inicio["datos"].get("tarea") or "",
            "inicio": t0, "ultimo_dato": max(ultimo_dato, t0),
            "pasos": {t: any(d.get("tipo") == t for d in sesion_docs) for t in PASOS_VIVO},
            "esp32": None if not ult else {
                "pulso_lpm": _num(ult_d.get("pulso_lpm")), "spo2": _num(ult_d.get("spo2")),
                "hrv_rmssd_ms": _num(ult_d.get("hrv_rmssd_ms")), "movimiento": _num(ult_d.get("movimiento")),
                "dedo": ult_d.get("dedo") is True, "calidad": _num(ult_d.get("calidad")),
                "simulado": bool(ult_d.get("simulado")), "fecha": _ms(ult.get("recibido")),
                # Vigente según cuándo llegó a Tierra (en la nave pasó hace «retraso» segundos más).
                "vigente": ahora_ms - (_ms(ult.get("llego_tierra")) or _ms(ult.get("recibido")) or 0) <= DATO_VIGENTE_S * 1000,
            },
            "lecturas_esp32": len(esp),
            "serie_pulso": [p for p in serie if p[1] is not None],
            "evaluacion": None if not ev else {
                "color": ev_d.get("color"), "puntaje": _num(ev_d.get("puntaje")), "motivos": ev_d.get("motivos") or [],
                "llego": _ms(ev.get("llego_tierra")), "provisional": bool(ev_d.get("provisional")),
            },
        })
    vivas.sort(key=lambda v: v["inicio"], reverse=True)
    return vivas


def armar_tablero(docs, estado: dict | None, equipo: list[str], ahora_ms: int, ultimas: int = 30,
                  en_camino: int = 0, por_llegar: list[dict] | None = None) -> dict:
    """Lo que ve Houston: lo que está pasando a bordo ahora, la última evaluación de cada tripulante, las últimas
    evaluaciones, lo que viene en camino, el copiloto y el enlace.

    `docs` son solo los que ya llegaron a Tierra; `por_llegar`, las evaluaciones que todavía vienen en camino
    ({persona, sesion, llega}: sin el color, que Tierra todavía no conoce)."""
    filas = filas_de(docs)
    fechas = [m for m in (_ms(d.get("recibido")) for d in docs) if m]
    ultima: dict[str, dict] = {}
    for f in filas:
        if f["persona"]:
            ultima[f["persona"]] = f
    personas = list(equipo) + sorted(p for p in ultima if p not in equipo)
    copiloto = [{"persona": d.get("persona"), "fecha": _ms(d.get("recibido")),
                 "pregunta": (d.get("datos") or {}).get("pregunta") or "",
                 "respuesta": (d.get("datos") or {}).get("respuesta") or ""}
                for d in docs if d.get("tipo") == "copiloto"]
    copiloto.sort(key=lambda c: c["fecha"] or 0, reverse=True)
    conteo = {"verde": 0, "amarillo": 0, "rojo": 0, "sin_dato": 0}
    for p in personas:
        color = (ultima.get(p) or {}).get("color")
        conteo[color if color in conteo else "sin_dato"] += 1
    return {
        "disponible": True,
        "ahora": ahora_ms,
        "enlace": estado_enlace(estado, ahora_ms, en_camino, max(fechas) if fechas else None),
        "conteo": conteo,
        "tripulacion": [{"persona": p, "ultima": ultima.get(p)} for p in personas],
        "evaluaciones": list(reversed(filas))[:ultimas],
        "en_vivo": en_vivo(docs, ahora_ms),
        "por_llegar": sorted(por_llegar or [], key=lambda x: x.get("llega") or 0),
        "copiloto": copiloto[:8],
    }


def a_csv(filas: list[dict]) -> str:
    def hora(ms):
        return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M:%S") if ms else ""

    salida = io.StringIO()
    w = csv.writer(salida, lineterminator="\r\n")
    w.writerow(COLUMNAS_CSV)
    for f in filas:
        valores = {**f, "fecha_nave": hora(f.get("fecha")), "llego_tierra": hora(f.get("llego")), "sesion": f["id"],
                   "pvt_mediana_ms": f.get("pvt_mediana"), "motivos": " | ".join(f.get("motivos") or [])}
        w.writerow(["" if valores.get(c) is None else str(valores.get(c)).lower() if isinstance(valores.get(c), bool)
                    else valores.get(c) for c in COLUMNAS_CSV])
    return salida.getvalue()


# ---------------------------------------------------------------- consultas (con MongoDB)

def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _consulta(dias: int = 0, persona: str = "", tipos=TIPOS) -> dict:
    q = {"tipo": {"$in": list(tipos)}, "reproducido": {"$ne": True}, "llego_tierra": {"$lte": _ahora()}}
    if dias > 0:
        q["recibido"] = {"$gte": datetime.now(timezone.utc) - timedelta(days=dias)}
    if persona:
        q["persona"] = persona.lower()
    return q


def _docs(q: dict, limite: int = MAX_DOCUMENTOS) -> list[dict]:
    """Los `limite` más NUEVOS que cumplen q, devueltos del más viejo al más nuevo (si sobran, se pierden los viejos)."""
    campos = {"_id": 0, "tipo": 1, "persona": 1, "recibido": 1, "llego_tierra": 1, "datos": 1}
    docs = list(base()[COLECCION].find(q, campos).sort("recibido", -1).limit(limite))
    docs.reverse()
    return docs


SIN_ESP32 = tuple(t for t in TIPOS if t != "esp32")


def _con_esp32(docs: list[dict], sesiones: set[str]) -> list[dict]:
    """docs + las lecturas del ESP32 (ya en Tierra) de esas sesiones. Las lecturas son una por segundo: solo se leen
    las de las sesiones que se van a mostrar, nunca todas."""
    if not sesiones:
        return docs
    esp = _docs({"tipo": "esp32", "datos.sesion": {"$in": sorted(sesiones)}, "reproducido": {"$ne": True},
                 "llego_tierra": {"$lte": _ahora()}})
    return docs + esp


def tablero(ultimas: int = 30) -> dict:
    try:
        ahora = _ahora()
        ahora_ms = int(ahora.timestamp() * 1000)
        docs = _docs(_consulta(tipos=SIN_ESP32))
        # Sesiones que se muestran: las últimas evaluaciones, la última de cada uno y las que están en curso.
        filas = filas_de(docs)
        sesiones = {f["id"] for f in filas[-ultimas:]}
        sesiones |= {f["id"] for f in {f["persona"]: f for f in filas}.values()}
        sesiones |= {(d.get("datos") or {}).get("sesion") for d in docs
                     if d.get("tipo") == "control/sesion" and ahora_ms - (_ms(d.get("recibido")) or 0) <= VIVO_MIN * 60_000}
        sesiones.discard(None)
        docs = _con_esp32(docs, sesiones)
        estado = base()[COLECCION_ENLACE].find_one({"_id": "estado"})
        en_camino = base()[COLECCION].count_documents({"llego_tierra": {"$gt": ahora}})
        por_llegar = [{"persona": d.get("persona"), "sesion": (d.get("datos") or {}).get("sesion"),
                       "llega": _ms(d.get("llego_tierra"))}
                      for d in base()[COLECCION].find({"tipo": "evaluacion", "llego_tierra": {"$gt": ahora},
                                                       "reproducido": {"$ne": True}},
                                                      {"_id": 0, "persona": 1, "datos.sesion": 1, "llego_tierra": 1}).limit(50)]
    except Exception as e:  # sin pymongo o sin MongoDB: la página lo muestra
        return _no_disponible(e)
    return armar_tablero(docs, estado, tripulacion(), ahora_ms, ultimas, en_camino=en_camino, por_llegar=por_llegar)


def evaluaciones(dias: int = 0, persona: str = "") -> dict:
    try:
        docs = _docs(_consulta(dias, persona, tuple(t for t in TIPOS_FILA if t != "esp32")))
        docs = _con_esp32(docs, {f["id"] for f in filas_de(docs)})
    except Exception as e:
        return _no_disponible(e)
    return {"disponible": True, "filas": filas_de(docs)}


def sesion(sid: str) -> dict:
    """Los mensajes de una sesión, para el detalle. Las lecturas del ESP32 van resumidas (no una por segundo)."""
    if not sid:
        return {"disponible": False, "motivo": "Falta el parámetro sesion."}
    try:
        docs = _docs({"datos.sesion": sid, "reproducido": {"$ne": True}, "tipo": {"$in": list(TIPOS)},
                      "llego_tierra": {"$lte": _ahora()}})
    except Exception as e:
        return _no_disponible(e)
    mensajes, esp32 = [], []
    for d in docs:
        if d.get("tipo") == "esp32":
            esp32.append(d.get("datos") or {})
            continue
        mensajes.append({"tipo": d.get("tipo"), "persona": d.get("persona"), "fecha": _ms(d.get("recibido")),
                         "llego": _ms(d.get("llego_tierra")), "datos": d.get("datos") or {}})
    return {"disponible": True, "sesion": sid, "mensajes": mensajes, "esp32": resumen_esp32(esp32)}


def resumen_esp32(lecturas: list[dict]) -> dict | None:
    if not lecturas:
        return None
    validas = [m for m in lecturas if m.get("dedo") is True and (_num(m.get("calidad")) or 0) >= CALIDAD_ESP32_MIN]

    def mediana(campo):
        v = [x for x in (_num(m.get(campo)) for m in validas) if x is not None]
        return round(statistics.median(v), 1) if v else None

    spo2 = [x for x in (_num(m.get("spo2")) for m in validas) if x is not None]
    return {"lecturas": len(lecturas), "validas": len(validas), "pulso_lpm": mediana("pulso_lpm"),
            "hrv_rmssd_ms": mediana("hrv_rmssd_ms"), "spo2": mediana("spo2"), "spo2_min": min(spo2) if spo2 else None,
            "simulado": any(m.get("simulado") for m in lecturas)}
