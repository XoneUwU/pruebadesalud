"""Prueba de los paneles web (no necesita el broker ni un navegador).

  python paneles/pruebas_paneles.py

- El servidor sirve las páginas, /config.js (con las credenciales según desde dónde se pida),
  vendor/mqtt.min.js, los íconos y la fuente, y no deja leer archivos fuera de paneles/web (como config.env).
- /historial.json, /historial.csv y /sesion.json responden aunque no estén pymongo ni MongoDB, y
  historial.filas_de() arma una fila por evaluación (sin MongoDB: con documentos de ejemplo).
- Nada se carga desde internet: ni scripts, ni estilos, ni fuentes.
- El JavaScript no tiene errores de sintaxis (node --check), logica.js da la misma recomendación
  que resumen_tripulacion() del copiloto y plantilla.js escapa los textos. Si no está Node, esas pruebas se saltan.
Muestra OK o FALLA por cada caso y termina con código 1 si alguno falla.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
WEB = AQUI / "web"
sys.path.insert(0, str(AQUI))
sys.path.insert(0, str(RAIZ / "copiloto"))

import historial  # noqa: E402
import servidor  # noqa: E402

fallas = 0
total = 0


def revisar(ok: bool, texto: str, detalle: str = ""):
    global fallas, total
    total += 1
    fallas += not ok
    print(f"{'OK   ' if ok else 'FALLA'}  {texto}")
    if not ok and detalle:
        print(f"       {detalle}")


def pedir(base: str, ruta: str) -> tuple[int, str, bytes]:
    try:
        with urllib.request.urlopen(base + ruta, timeout=5) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), b""


def probar_servidor():
    print("--- servidor ---")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), servidor.Manejador)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    servidor.Manejador.log_message = lambda *a: None  # sin el registro de cada petición
    try:
        for ruta in ("/", "/estacion.html", "/tripulacion.html", "/tierra.html"):
            codigo, tipo, cuerpo = pedir(base, ruta)
            revisar(codigo == 200 and tipo.startswith("text/html") and b"</html>" in cuerpo,
                    f"GET {ruta} -> {codigo} {tipo}")
        for ruta, esperado in (("/nocturne.css", "text/css"), ("/app.css", "text/css"), ("/vendor/phosphor/regular.css", "text/css"),
                               ("/vendor/phosphor/Phosphor-Fill.woff2", "font/woff2"),
                               ("/vendor/inter/inter-latin-500-normal.woff2", "font/woff2")):
            codigo, tipo, cuerpo = pedir(base, ruta)
            revisar(codigo == 200 and tipo.startswith(esperado) and len(cuerpo) > 1000, f"GET {ruta} -> {codigo} {tipo}")
        for ruta, esperado in (("/historial.json?dias=7", "application/json"), ("/sesion.json?sesion=x", "application/json"),
                               ("/historial.csv?persona=bri", "text/csv")):
            codigo, tipo, cuerpo = pedir(base, ruta)
            ok = codigo == 200 and tipo.startswith(esperado)
            if ok and esperado == "application/json":
                ok = "disponible" in json.loads(cuerpo.decode("utf-8"))
            revisar(ok, f"GET {ruta} -> {codigo} {tipo} (responde aunque no esté MongoDB)")

        codigo, tipo, cuerpo = pedir(base, "/config.js")
        texto = cuerpo.decode("utf-8")
        datos = json.loads(texto[texto.index("{"):texto.rindex("}") + 1]) if "{" in texto else {}
        revisar(codigo == 200 and tipo.startswith("text/javascript") and "window.APTO" in texto,
                f"GET /config.js -> {codigo} {tipo}")
        revisar(datos.get("puede_publicar") is True and datos.get("mqtt_puerto_ws") == 9001,
                "config.js desde localhost: puede publicar, WebSocket 9001", str(datos))
        frases = datos.get("frases_voz", {})
        revisar(list(frases)[:1] == ["estandar"] and "trabalenguas" in frases and len(frases) >= 3
                and all(f.get("texto") for f in frases.values()),
                f"config.js trae las frases de voz para elegir: {list(frases)}")
        revisar(all(k in datos for k in ("camara", "vision_segundos", "ollama_model", "mongo_db", "mongo_host"))
                and "mongodb" not in str(datos.get("mongo_host")),
                "config.js trae lo que muestra Configuración (cámara, visión, modelos, MongoDB sin la URI)")
        revisar(len(datos.get("tripulacion", [])) >= 1 and datos.get("pvt_segundos", 0) > 0
                and "retraso_tierra_s" in datos and "caminata" in datos.get("frase_voz", ""),
                f"config.js trae tripulación {datos.get('tripulacion')}, PVT {datos.get('pvt_segundos')} s, "
                f"retraso {datos.get('retraso_tierra_s')} s y la frase de voz")

        codigo, tipo, cuerpo = pedir(base, "/vendor/mqtt.min.js")
        revisar(codigo == 200 and tipo.startswith("text/javascript") and len(cuerpo) > 100_000
                and cuerpo.startswith(b'"use strict";var mqtt='),
                f"GET /vendor/mqtt.min.js -> {codigo}, {len(cuerpo) // 1024} KB, servido desde paneles/web/vendor")

        for ruta in ("/../config.env", "/%2e%2e/config.env", "/..%2f..%2fconfig.env", "/vendor/"):
            codigo, _, cuerpo = pedir(base, ruta)
            revisar(codigo == 404 and b"MQTT_HOST" not in cuerpo, f"GET {ruta} -> {codigo} (no sale de paneles/web)")
    finally:
        srv.shutdown()
        srv.server_close()


def probar_credenciales():
    print("\n--- credenciales de /config.js ---")
    antes = {k: os.environ.get(k) for k in ("MQTT_USER", "MQTT_PASS", "MQTT_USER_LECTURA", "MQTT_PASS_LECTURA")}
    os.environ.update(MQTT_USER="sistema-prueba", MQTT_PASS="clave-sistema",
                      MQTT_USER_LECTURA="equipo-prueba", MQTT_PASS_LECTURA="clave-equipo")
    try:
        local, otra = servidor.configuracion(True), servidor.configuracion(False)
        revisar(local["mqtt_usuario"] == "sistema-prueba" and local["mqtt_clave"] == "clave-sistema"
                and local["puede_publicar"], "desde localhost: MQTT_USER y MQTT_PASS (puede publicar)")
        revisar(otra["mqtt_usuario"] == "equipo-prueba" and otra["mqtt_clave"] == "clave-equipo"
                and not otra["puede_publicar"], "desde otra laptop: MQTT_USER_LECTURA y MQTT_PASS_LECTURA (solo lectura)")
    finally:
        for k, v in antes.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    casos = {"127.0.0.1": True, "::1": True, "::ffff:127.0.0.1": True, "192.168.1.20": False, "10.0.0.5": False}
    malos = {ip: esperado for ip, esperado in casos.items() if servidor.es_local(ip) != esperado}
    revisar(not malos, f"es_local: {', '.join(f'{ip}={v}' for ip, v in casos.items())}", f"fallan: {malos}")


def probar_sin_internet():
    print("\n--- nada desde internet ---")
    externo_html = re.compile(r"""(src|href)\s*=\s*["']\s*(https?:)?//""", re.I)
    externo_css = re.compile(r"""(url\(\s*["']?\s*(https?:)?//|@import)""", re.I)
    # http://www.w3.org/2000/svg es el nombre del espacio de SVG (createElementNS), no una descarga
    externo_js = re.compile(r"""(https?:)?//(?!www\.w3\.org/)[a-z0-9.-]+\.[a-z]{2,}/|import\s*\(|importScripts""", re.I)
    for ruta in sorted(WEB.rglob("*")):
        if not ruta.is_file() or "vendor" in ruta.parts:
            continue
        patron = {".html": externo_html, ".css": externo_css, ".js": externo_js}.get(ruta.suffix)
        if patron:  # solo los archivos de texto (las imágenes, como assets/fondo-luna.png, no se leen)
            texto = ruta.read_text(encoding="utf-8")
            hallado = patron.search(texto)
            revisar(not hallado, f"{ruta.relative_to(AQUI)}: sin recursos externos",
                    f"encontrado: {hallado.group(0) if hallado else ''}")
    esperados = ["config.js", "vendor/mqtt.min.js", "logica.js", "comun.js", "plantilla.js", "logo.js", "fondo.js", "estacion.js"]
    for pagina in ("estacion.html", "tripulacion.html"):
        scripts = re.findall(r"""<script[^>]*src=["']([^"']+)""", (WEB / pagina).read_text(encoding="utf-8"))
        revisar(scripts == esperados, f"{pagina} carga solo scripts locales: {scripts}")


def probar_javascript():
    print("\n--- JavaScript (Node) ---")
    node = shutil.which("node")
    if not node:
        print("SALTADA  No está Node: no se revisa la sintaxis del JavaScript.")
        return
    for ruta in sorted(WEB.rglob("*.js")):
        r = subprocess.run([node, "--check", str(ruta)], capture_output=True, text=True, encoding="utf-8")
        revisar(r.returncode == 0, f"node --check {ruta.relative_to(AQUI)}", r.stderr.strip()[:300])

    from copiloto import con_articulo, resumen_tripulacion

    def ev(p, c, pts, tarea="caminata espacial"):
        return {"persona": p, "color": c, "puntaje": pts, "tarea": tarea}

    escenarios = [
        ({"bri": ev("bri", "amarillo", 0.62), "eric": ev("eric", "verde", 0.88), "sebas": ev("sebas", "verde", 0.81),
          "adrian": ev("adrian", "amarillo", 0.58), "danilo": ev("danilo", "rojo", 0.31)}, "caminata espacial"),
        ({"bri": ev("bri", "amarillo", 0.62), "danilo": ev("danilo", "rojo", 0.31),
          "adrian": ev("adrian", "rojo", 0.4)}, "maniobra de acoplamiento"),
        ({"eric": ev("eric", "verde", 0.88)}, "mantenimiento externo"),
        ({}, "caminata espacial"),
        ({"bri": ev("bri", "verde", 0.7), "sebas": ev("sebas", "amarillo", 0.6), "adrian": ev("adrian", "amarillo", 0.5),
          "danilo": ev("danilo", "rojo", 0.3), "eric": ev("eric", "rojo", 0.2)}, ""),
        ({"bri": ev("bri", "verde", 0.8), "eric": ev("eric", "verde", 0.8)}, "caminata espacial"),  # empate: orden de llegada
    ]
    tareas = ["caminata espacial", "maniobra de acoplamiento", "mantenimiento externo", "la caminata"]
    programa = r"""
const L = require(process.argv[1]);
let s = "";
process.stdin.on("data", (d) => (s += d));
process.stdin.on("end", () => {
  const c = JSON.parse(s);
  console.log(JSON.stringify({
    recomendaciones: c.escenarios.map(([evs, t]) => L.recomendacion(evs, t).texto),
    articulos: c.tareas.map(L.conArticulo),
    pvt: L.resumenPvt([250, 300, 400, 120], 2, 1, 7, 61234),
    clasificacion: [99, 100, 354, 355].map(L.clasificarRespuesta),
    dsst: L.resumenDsst(45, 3, 90000),
    simbolos: [L.SIMBOLOS_DSST.length, new Set(L.SIMBOLOS_DSST).size, L.DSST_SEGUNDOS, L.DSST_DEMO_S, L.PVT.DEMO_S],
  }));
});
"""
    plantilla = r"""
const P = require(process.argv[1]);
console.log(String(P.h`<p title="${'a"b'}">${"<img src=x onerror=1>"}${[P.h`<i>${1}</i>`, null, false]}</p>`));
"""
    r = subprocess.run([node, "-e", plantilla, str(WEB / "plantilla.js")], capture_output=True, text=True, encoding="utf-8")
    revisar(r.stdout.strip() == '<p title="a&quot;b">&lt;img src=x onerror=1&gt;<i>1</i></p>',
            f"plantilla.js escapa textos y atributos: {r.stdout.strip() or r.stderr.strip()[:200]}")

    r = subprocess.run([node, "-e", programa, str(WEB / "logica.js")], input=json.dumps({"escenarios": escenarios, "tareas": tareas}),
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        revisar(False, "logica.js se ejecuta en Node", r.stderr.strip()[:500])
        return
    js = json.loads(r.stdout)
    for (evs, tarea), texto_js in zip(escenarios, js["recomendaciones"]):
        texto_py = resumen_tripulacion(evs, tarea, "")
        revisar(texto_js == texto_py, f"recomendación igual al copiloto ({len(evs)} evaluaciones, tarea {tarea or '-'!r})",
                f"\n         JS: {texto_js}\n         PY: {texto_py}")
    revisar(js["articulos"] == [con_articulo(t) for t in tareas], f"conArticulo igual al copiloto: {js['articulos']}")
    revisar(js["pvt"] == {"rt_media_ms": 268, "rt_mediana_ms": 275, "lapsos": 2, "anticipadas": 2,
                          "lapsos_por_min": 1.96, "anticipadas_por_min": 1.96, "n_estimulos": 7, "duracion_s": 61.2},
            f"resumenPvt (con lapsos y anticipadas por minuto): {js['pvt']}")
    revisar(js["clasificacion"] == ["anticipada", "valida", "valida", "lapso"],
            f"PVT 99/100/354/355 ms: {js['clasificacion']}")
    revisar(js["dsst"] == {"correctas": 45, "incorrectas": 3, "por_minuto": 30, "duracion_s": 90},
            f"resumenDsst: {js['dsst']}")
    revisar(js["simbolos"] == [9, 9, 90, 40, 40], f"DSST: 9 símbolos distintos, 90 s (40 en demo); PVT demo 40 s: {js['simbolos']}")


def probar_historial():
    print("\n--- historial (sin MongoDB) ---")
    from datetime import datetime, timedelta, timezone
    t0 = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)

    def doc(seg, tipo, datos, persona="bri"):
        return {"recibido": t0 + timedelta(seconds=seg), "tipo": tipo, "persona": persona, "datos": datos}

    s1, s2 = "20261113-120000-bri", "20261113-130000-eric"
    docs = [
        doc(0, "control/sesion", {"sesion": s1, "tarea": "caminata espacial"}),
        *[doc(1 + i, "esp32", {"sesion": s1, "dedo": True, "calidad": 0.8, "pulso_lpm": p}) for i, p in enumerate((60, 70, 80))],
        doc(4, "esp32", {"sesion": s1, "dedo": False, "calidad": 0.9, "pulso_lpm": 150}),  # sin dedo: no cuenta
        doc(10, "pvt", {"sesion": s1, "rt_mediana_ms": 312}),
        doc(20, "vision", {"sesion": s1, "perclos": 8}),  # en porcentaje
        doc(30, "cuestionario", {"sesion": s1, "kss": 6, "horas_sueno": 5.5}),
        doc(31, "evaluacion", {"sesion": s1, "color": "verde", "puntaje": 1.0, "motivos": []}),
        doc(40, "evaluacion", {"sesion": s1, "color": "amarillo", "puntaje": 0.75, "motivos": ["Menos de 6 horas de sueño"],
                               "provisional": True}),  # el coordinador recalculó: vale esta
        doc(100, "cuestionario", {"sesion": s2, "kss": 8}, "eric"),  # sesión sin evaluación: no es fila
        doc(200, "evaluacion", {"color": "rojo"}, "eric"),  # sin sesión: no es fila
    ]
    filas = historial.filas_de(docs)
    f = filas[0] if filas else {}
    revisar(len(filas) == 1 and f["id"] == s1 and f["color"] == "amarillo" and f["puntaje"] == 0.75 and f["provisional"],
            f"una fila por sesión con evaluación, con la última evaluación: {[(x['id'], x['color']) for x in filas]}")
    revisar(f.get("pulso_lpm") == 70 and f.get("pvt_mediana") == 312 and f.get("kss") == 6 and f.get("horas_sueno") == 5.5
            and f.get("perclos") == 0.08 and f.get("tarea") == "caminata espacial",
            f"pulso = mediana con dedo, PVT, KSS, sueño, PERCLOS en fracción y tarea de la sesión: {f}")
    csv_texto = historial.a_csv(filas)
    revisar(csv_texto.startswith("fecha,persona,sesion") and s1 in csv_texto and "Menos de 6 horas de sueño" in csv_texto,
            "a_csv: encabezado, sesión y motivos")


def main() -> int:
    probar_servidor()
    probar_historial()
    probar_credenciales()
    probar_sin_internet()
    probar_javascript()
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
