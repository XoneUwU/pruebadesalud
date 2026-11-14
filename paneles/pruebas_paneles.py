"""Prueba de los paneles web (no necesita el broker ni un navegador).

  python paneles/pruebas_paneles.py

- El servidor sirve las páginas, /config.js (con las credenciales según desde dónde se pida) y
  vendor/mqtt.min.js, y no deja leer archivos fuera de paneles/web (como config.env).
- Nada se carga desde internet: ni scripts, ni estilos, ni fuentes.
- El JavaScript no tiene errores de sintaxis (node --check) y logica.js da la misma recomendación
  que resumen_tripulacion() del copiloto. Si no está Node, esas pruebas se saltan.
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
        texto = ruta.read_text(encoding="utf-8")
        patron = {".html": externo_html, ".css": externo_css, ".js": externo_js}.get(ruta.suffix)
        if patron:
            hallado = patron.search(texto)
            revisar(not hallado, f"{ruta.relative_to(AQUI)}: sin recursos externos",
                    f"encontrado: {hallado.group(0) if hallado else ''}")
    scripts = re.findall(r"""<script[^>]*src=["']([^"']+)""", (WEB / "estacion.html").read_text(encoding="utf-8"))
    revisar(scripts == ["config.js", "vendor/mqtt.min.js", "logica.js", "comun.js", "estacion.js"],
            f"estacion.html carga solo scripts locales: {scripts}")


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
        ({"bri": ev("bri", "amarillo", 0.62), "erick": ev("erick", "verde", 0.88), "sebas": ev("sebas", "verde", 0.81),
          "adrian": ev("adrian", "amarillo", 0.58), "danilo": ev("danilo", "rojo", 0.31)}, "caminata espacial"),
        ({"bri": ev("bri", "amarillo", 0.62), "danilo": ev("danilo", "rojo", 0.31),
          "adrian": ev("adrian", "rojo", 0.4)}, "maniobra de acoplamiento"),
        ({"erick": ev("erick", "verde", 0.88)}, "mantenimiento externo"),
        ({}, "caminata espacial"),
        ({"bri": ev("bri", "verde", 0.7), "sebas": ev("sebas", "amarillo", 0.6), "adrian": ev("adrian", "amarillo", 0.5),
          "danilo": ev("danilo", "rojo", 0.3), "erick": ev("erick", "rojo", 0.2)}, ""),
        ({"bri": ev("bri", "verde", 0.8), "erick": ev("erick", "verde", 0.8)}, "caminata espacial"),  # empate: orden de llegada
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
    simbolos: [L.SIMBOLOS_DSST.length, new Set(L.SIMBOLOS_DSST).size, L.DSST_SEGUNDOS],
  }));
});
"""
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
    revisar(js["simbolos"] == [9, 9, 90], f"DSST: 9 símbolos distintos y 90 s: {js['simbolos']}")


def main() -> int:
    probar_servidor()
    probar_credenciales()
    probar_sin_internet()
    probar_javascript()
    print(f"\n{total - fallas} de {total} pasaron.")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
