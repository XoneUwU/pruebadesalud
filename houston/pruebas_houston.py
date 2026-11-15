"""Prueba de Houston (no necesita MongoDB, el broker ni un navegador).

  python houston/pruebas_houston.py

- modelo.filas_de() arma una fila por evaluación (la última si el coordinador recalculó, el pulso como mediana del
  ESP32 válido) y armar_tablero() da la última por tripulante, el conteo de colores y la señal del enlace.
- receptor.documento() guarda solo los tipos de Tierra con su retraso, y un mensaje retenido no se guarda dos veces.
- El servidor sirve la vista y las rutas de la API (con el modelo reemplazado por datos de ejemplo), responde
  {"disponible": false} sin MongoDB y no deja leer archivos fuera de houston/web.
- La vista no carga nada de internet y houston.js no tiene errores de sintaxis (node --check; si no está Node, se salta).
Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import json
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import controlador  # noqa: E402
import modelo  # noqa: E402
import receptor  # noqa: E402

fallas = 0
total = 0
T0 = datetime(2026, 11, 14, 15, 0, tzinfo=timezone.utc)


def revisar(ok: bool, texto: str, detalle: str = ""):
    global fallas, total
    total += 1
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  {texto}")
    if not ok and detalle:
        print(f"       {detalle}")


def doc(tipo, persona, seg, datos, llego_seg=None):
    return {"tipo": tipo, "persona": persona, "recibido": T0 + timedelta(seconds=seg),
            "llego_tierra": T0 + timedelta(seconds=llego_seg if llego_seg is not None else seg + 20), "datos": datos}


def ejemplo():
    s1, s2 = "20261114-150000-bri", "20261114-151000-erick"
    return [
        doc("control/sesion", None, 0, {"persona": "bri", "tarea": "EVA", "sesion": s1}),
        doc("esp32", "bri", 1, {"sesion": s1, "dedo": True, "calidad": 0.9, "pulso_lpm": 70, "spo2": 97}),
        doc("esp32", "bri", 2, {"sesion": s1, "dedo": True, "calidad": 0.9, "pulso_lpm": 74, "spo2": 95}),
        doc("esp32", "bri", 3, {"sesion": s1, "dedo": True, "calidad": 0.2, "pulso_lpm": 150, "spo2": 80}),
        doc("esp32", "bri", 4, {"sesion": s1, "dedo": False, "calidad": 0.9, "pulso_lpm": None}),
        doc("pvt", "bri", 200, {"sesion": s1, "rt_mediana_ms": 280, "lapsos": 1}),
        doc("cuestionario", "bri", 230, {"sesion": s1, "kss": 7, "horas_sueno": 5.5}),
        doc("evaluacion", "bri", 232, {"sesion": s1, "color": "amarillo", "puntaje": 2, "motivos": ["A"]}),
        doc("evaluacion", "bri", 240, {"sesion": s1, "color": "rojo", "puntaje": 4, "motivos": ["A", "B"],
                                       "provisional": True}),
        doc("evaluacion", "erick", 600, {"sesion": s2, "color": "verde", "puntaje": 0, "motivos": []}),
        doc("pvt", "danilo", 700, {"sesion": "sin-evaluacion", "rt_mediana_ms": 300}),
        doc("copiloto", "bri", 250, {"pregunta": "¿Cómo estoy?", "respuesta": "Rojo."}),
    ]


def probar_modelo():
    print("--- modelo ---")
    filas = modelo.filas_de(ejemplo())
    revisar(len(filas) == 2, "una fila por sesión con evaluación (la de sin evaluación no cuenta)", str(filas))
    bri = filas[0]
    revisar(bri["color"] == "rojo" and bri["puntaje"] == 4, "vale la última evaluación si el coordinador recalculó")
    revisar(bri["pulso_lpm"] == 72.0, "pulso = mediana de las lecturas con dedo y calidad >= 0,5", str(bri["pulso_lpm"]))
    revisar(bri["spo2_min"] == 95, "SpO2 mínimo solo de lecturas válidas", str(bri["spo2_min"]))
    revisar(bri["tarea"] == "EVA" and bri["kss"] == 7 and bri["pvt_mediana"] == 280, "tarea, KSS y PVT de la sesión")
    revisar(bri["llego"] - bri["fecha"] == 20_000, "guarda cuándo llegó a Tierra")

    ahora = int((T0 + timedelta(seconds=700)).timestamp() * 1000)
    estado = {"actualizado": T0 + timedelta(seconds=690), "retraso_s": 20, "guardados": 12, "conectado": True}
    t = modelo.armar_tablero(ejemplo(), estado, ["bri", "danilo", "erick"], ahora, en_camino=3)
    revisar([x["persona"] for x in t["tripulacion"]] == ["bri", "danilo", "erick"], "una tarjeta por tripulante")
    revisar(t["conteo"] == {"verde": 1, "amarillo": 0, "rojo": 1, "sin_dato": 1}, "conteo por color", str(t["conteo"]))
    revisar(t["evaluaciones"][0]["persona"] == "erick", "las evaluaciones van de la más nueva a la más vieja")
    revisar(t["enlace"]["con_senal"] and t["enlace"]["en_camino"] == 3 and t["enlace"]["copiados"] == 12,
            "enlace con señal", str(t["enlace"]))
    revisar(t["enlace"]["ultimo_dato_nave"] == int((T0 + timedelta(seconds=700)).timestamp() * 1000),
            "último dato de la nave = el más nuevo que ya llegó")
    revisar(len(t["copiloto"]) == 1 and t["copiloto"][0]["respuesta"] == "Rojo.", "conversaciones del copiloto")
    sin = modelo.estado_enlace(estado, ahora + 60_000)
    revisar(not sin["con_senal"] and sin["error"], "sin señal si el receptor no actualiza en 30 s")
    revisar(not modelo.estado_enlace({**estado, "conectado": False}, ahora)["con_senal"], "sin señal sin Mosquitto")
    revisar(not modelo.estado_enlace(None, ahora)["con_senal"], "sin señal si el receptor nunca corrió")

    texto = modelo.a_csv(filas)
    lineas = texto.strip().splitlines()
    revisar(len(lineas) == 3 and lineas[0].startswith("fecha_nave,llego_tierra"), "CSV con encabezado y una línea por fila")
    revisar("A | B" in texto and ",true," in texto, "CSV: motivos unidos y booleanos en minúscula")
    r = modelo.resumen_esp32([d["datos"] for d in ejemplo() if d["tipo"] == "esp32"])
    revisar(r["lecturas"] == 4 and r["validas"] == 2 and r["pulso_lpm"] == 72.0, "resumen del ESP32 para el detalle", str(r))


class ColeccionFalsa:
    """Lo mínimo de una colección de pymongo para probar Receptor.guardar() sin MongoDB."""

    def __init__(self):
        self.docs = []

    def insert_one(self, doc):
        self.docs.append(doc)

    def update_one(self, filtro, cambio, upsert=False):
        def coincide(d):
            for k, v in filtro.items():
                x = d
                for parte in k.split("."):
                    x = (x or {}).get(parte)
                if x != v:
                    return False
            return True

        class R:
            upserted_id = None
        if not any(coincide(d) for d in self.docs) and upsert:
            self.docs.append(dict(cambio["$setOnInsert"]))
            R.upserted_id = len(self.docs)
        return R()


def probar_receptor():
    print("--- receptor ---")
    d = receptor.documento("apto/bri/evaluacion", {"sesion": "s1", "color": "rojo"}, 20, T0)
    revisar(d["persona"] == "bri" and d["tipo"] == "evaluacion", "persona y tipo salen del tema")
    revisar(d["llego_tierra"] - d["recibido"] == timedelta(seconds=20), "llega a Tierra con el retraso")
    revisar(receptor.documento("apto/control/sesion", {"persona": "bri", "sesion": "s1"}, 0, T0)["persona"] == "bri",
            "control/sesion baja con la persona del mensaje")
    revisar(all(receptor.documento(t, {}, 0, T0) is None for t in
                ("apto/control/orden_voz", "apto/control/modulos/voz", "apto/control/estado_vision", "apto/bri/semaforo")),
            "no bajan órdenes, estados de los módulos ni el semáforo")
    revisar(receptor.documento("apto/bri/esp32", 5, 0, T0)["datos"] == {"valor": 5}, "un dato que no es objeto no falla")

    col = ColeccionFalsa()
    r = receptor.Receptor(col, None, 20)
    datos = {"sesion": "s1", "ts": "2026-11-14T15:00:00", "color": "rojo"}
    revisar(r.guardar("apto/bri/evaluacion", datos, retenido=True), "un retenido nuevo se guarda")
    revisar(not r.guardar("apto/bri/evaluacion", datos, retenido=True), "el mismo retenido no se guarda dos veces")
    revisar(col.docs[0]["llego_tierra"] == col.docs[0]["recibido"], "lo retenido ya está en Tierra (sin retraso)")
    revisar(r.guardar("apto/bri/pvt", {"sesion": "s1"}) and not r.guardar("apto/control/orden_vision", {}),
            "guarda los datos y descarta las órdenes")
    revisar(r.guardados == 2 and len(col.docs) == 2, "cuenta solo lo guardado")


def pedir(base: str, ruta: str):
    try:
        with urllib.request.urlopen(base + ruta, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), b""


def probar_servidor():
    print("--- servidor ---")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), controlador.Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        estado, tipo, cuerpo = pedir(base, "/")
        revisar(estado == 200 and "html" in tipo and b"Houston" in cuerpo, "sirve la vista")
        estado, tipo, _ = pedir(base, "/houston.js")
        revisar(estado == 200 and "javascript" in tipo, "houston.js con el tipo correcto")
        for ruta in ("/../config.env", "/%2e%2e/config.env", "/../modelo.py"):
            estado, _, cuerpo = pedir(base, ruta)
            revisar(estado == 404 or b"MONGO" not in cuerpo and b"import" not in cuerpo, f"no sirve {ruta}")
        revisar(pedir(base, "/api/otra.json")[0] == 404, "ruta de API desconocida: 404")

        # Sin MongoDB (o sin pymongo) responde igual, con disponible: false.
        modelo._cliente = None
        viejo_uri = modelo.config.get
        modelo.config.get = lambda k, d="": "mongodb://127.0.0.1:1" if k == "HOUSTON_MONGO_URI" else viejo_uri(k, d)
        try:
            estado, _, cuerpo = pedir(base, "/api/tablero.json")
            datos = json.loads(cuerpo)
            revisar(estado == 200 and datos.get("disponible") is False and datos.get("motivo"), "sin MongoDB: disponible false")
        finally:
            modelo.config.get = viejo_uri
            modelo._cliente = None

        # Con el modelo reemplazado por datos de ejemplo.
        filas = modelo.filas_de(ejemplo())
        originales = modelo.tablero, modelo.evaluaciones, modelo.sesion
        pedidos = {}
        modelo.tablero = lambda: modelo.armar_tablero(ejemplo(), None, ["bri"], 0)
        modelo.evaluaciones = lambda dias, persona: pedidos.update(dias=dias, persona=persona) or {"disponible": True, "filas": filas}
        modelo.sesion = lambda sid: {"disponible": True, "sesion": sid, "mensajes": [], "esp32": None}
        try:
            datos = json.loads(pedir(base, "/api/tablero.json")[2])
            revisar(datos["tripulacion"][0]["ultima"]["color"] == "rojo", "/api/tablero.json")
            datos = json.loads(pedir(base, "/api/evaluaciones.json?dias=7&persona=Bri<x>")[2])
            revisar(len(datos["filas"]) == 2 and pedidos == {"dias": 7, "persona": "brix"},
                    "/api/evaluaciones.json limpia persona y días", str(pedidos))
            estado, tipo, cuerpo = pedir(base, "/api/evaluaciones.csv?dias=abc")
            revisar(estado == 200 and "csv" in tipo and pedidos["dias"] == 0 and b"fecha_nave" in cuerpo,
                    "/api/evaluaciones.csv (días inválidos = todo)")
            datos = json.loads(pedir(base, "/api/sesion.json?sesion=" + "x" * 200)[2])
            revisar(len(datos["sesion"]) == 80, "/api/sesion.json corta el id a 80 caracteres")
        finally:
            modelo.tablero, modelo.evaluaciones, modelo.sesion = originales
    finally:
        srv.shutdown()
        srv.server_close()


def probar_vista():
    print("--- vista ---")
    externos = []
    for archivo in (AQUI / "web").rglob("*"):
        if archivo.suffix in (".html", ".css", ".js"):
            texto = archivo.read_text(encoding="utf-8")
            externos += [f"{archivo.name}: {u}" for u in re.findall(r"(?:src|href)=[\"'](https?:)?//[^\"']+", texto)]
            externos += [f"{archivo.name}: {u}" for u in re.findall(r"url\(\s*[\"']?https?://[^)]+\)", texto)]
    revisar(not externos, "nada se carga desde internet", "; ".join(externos))
    js = (AQUI / "web" / "houston.js").read_text(encoding="utf-8")
    revisar("innerHTML" not in js, "houston.js no usa innerHTML (los datos entran como texto)")
    node = shutil.which("node")
    if not node:
        print("(sin Node: se salta node --check)")
        return
    r = subprocess.run([node, "--check", str(AQUI / "web" / "houston.js")], capture_output=True, text=True)
    revisar(r.returncode == 0, "houston.js sin errores de sintaxis", r.stderr.strip())


if __name__ == "__main__":
    probar_modelo()
    probar_receptor()
    probar_servidor()
    probar_vista()
    print(f"\n{total - fallas} de {total} bien.")
    sys.exit(1 if fallas else 0)
