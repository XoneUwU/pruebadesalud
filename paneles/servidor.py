"""Servidor de los paneles web: sirve paneles/web/ y genera /config.js desde config.env.

  python paneles/servidor.py                 http://localhost:8080 en esta laptop
                                             http://IP-de-esta-laptop:8080 desde las demás
  python paneles/servidor.py --host 127.0.0.1    solo esta laptop (para probar)

Las páginas se conectan al broker por WebSocket (MQTT_WS_PORT, 9001) en el mismo host desde el que se
abrieron. /config.js lleva las credenciales: si la página se abre en esta misma laptop (localhost), las
de MQTT_USER, que puede publicar; si se abre desde otra laptop, las de solo lectura (MQTT_USER_LECTURA).
/historial.json, /historial.csv y /sesion.json leen el MongoDB del registrador (ver historial.py); si falta
pymongo o MongoDB, responden {"disponible": false} y el resto sigue igual. Si cambian config.env, reinicien
el servidor.
"""
import argparse
import ast
import json
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from comun import config  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import historial  # noqa: E402

WEB = Path(__file__).resolve().parent / "web"
PUERTO = 8080


def es_local(ip: str) -> bool:
    """La petición viene de esta misma laptop."""
    return ip in ("::1", "localhost") or ip.startswith("127.") or ip.startswith("::ffff:127.")


def constante_voz(nombre: str, defecto):
    """Una constante literal de voz/voz_fatiga.py, leída sin importar el módulo (así no hace falta Praat aquí)."""
    try:
        arbol = ast.parse((RAIZ / "voz" / "voz_fatiga.py").read_text(encoding="utf-8"))
        for nodo in arbol.body:
            if isinstance(nodo, ast.Assign) and any(getattr(t, "id", "") == nombre for t in nodo.targets):
                return ast.literal_eval(nodo.value)
    except (OSError, SyntaxError, ValueError):
        pass
    return defecto


def frase_voz() -> str:
    return constante_voz("FRASE", "")


def frases_voz() -> dict:
    """{"estandar": {"titulo", "texto"}, "variacion_1": ..., "trabalenguas": ...} para elegir en la estación."""
    frases = {"estandar": {"titulo": "Frase estándar", "texto": frase_voz()}}
    for clave, (titulo, texto) in constante_voz("VARIACIONES", {}).items():
        frases[clave] = {"titulo": titulo, "texto": texto}
    return frases


def host_mongo() -> str:
    """Solo el host de MONGO_URI, sin usuario ni clave (para mostrarlo en Configuración)."""
    try:
        return urlsplit(config.get("MONGO_URI", "mongodb://localhost:27017")).hostname or ""
    except ValueError:
        return ""


def configuracion(local: bool) -> dict:
    """Lo que reciben las páginas en window.APTO."""
    usuario, clave = ("MQTT_USER", "MQTT_PASS") if local else ("MQTT_USER_LECTURA", "MQTT_PASS_LECTURA")
    return {
        "mqtt_puerto_ws": config.get_int("MQTT_WS_PORT", 9001),
        "mqtt_usuario": config.get(usuario),
        "mqtt_clave": config.get(clave),
        "puede_publicar": local,
        "tripulacion": [p.strip().lower() for p in config.get("TRIPULACION").split(",") if p.strip()],
        "pvt_segundos": config.get_int("PVT_SEGUNDOS", 180),
        "retraso_tierra_s": config.get_int("RETRASO_TIERRA_S", 20),
        "frase_voz": frase_voz(),
        "frases_voz": frases_voz(),
        # Para Configuración (solo se muestran; se cambian en config.local.env).
        "mqtt_host": config.get("MQTT_HOST", "localhost"),
        "mqtt_puerto": config.get_int("MQTT_PORT", 1883),
        "camara": config.get("CAMARA", "0"),
        "vision_segundos": config.get_int("VISION_SEGUNDOS", 60),
        "ollama_model": config.get("OLLAMA_MODEL"),
        "whisper_model": config.get("WHISPER_MODEL"),
        "mongo_host": host_mongo(),
        "mongo_db": config.get("MONGO_DB", "apto_hoy"),
    }


def config_js(local: bool) -> bytes:
    datos = json.dumps(configuracion(local), ensure_ascii=False, indent=2)
    return f"// Generado por paneles/servidor.py desde config.env. No editar.\nwindow.APTO = {datos};\n".encode("utf-8")


class Manejador(SimpleHTTPRequestHandler):
    # En Windows el registro puede decir que .js es text/plain; aquí se fija.
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".md": "text/plain; charset=utf-8",
        ".woff2": "font/woff2",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        # Nada se guarda en la caché del navegador: tras actualizar el proyecto, la estación siempre carga la versión
        # nueva (con una versión vieja en caché, la página no entendía los mensajes nuevos del ESP32).
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def responder(self, cuerpo: bytes, tipo: str, extra: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        ruta = self.path.split("?", 1)[0].split("#", 1)[0]
        q = {k: v[-1] for k, v in parse_qs(urlsplit(self.path).query).items()}
        if ruta == "/config.js":
            self.responder(config_js(es_local(self.client_address[0])), "text/javascript; charset=utf-8")
            return
        if ruta in ("/historial.json", "/historial.csv", "/sesion.json"):
            try:
                dias = max(0, int(q.get("dias") or 0))
            except ValueError:
                dias = 0
            persona = "".join(c for c in q.get("persona", "").lower() if c.isalnum())
            if ruta == "/sesion.json":
                datos = historial.sesion(q.get("sesion", "")[:80])
            else:
                datos = historial.historial(dias, persona)
            if ruta == "/historial.csv":
                texto = historial.a_csv(datos.get("filas", [])) if datos.get("disponible") else f"# {datos.get('motivo')}\r\n"
                nombre = f"historial-{persona or 'tripulacion'}-{dias or 'todo'}.csv"
                self.responder(texto.encode("utf-8-sig"), "text/csv; charset=utf-8",
                               {"Content-Disposition": f'attachment; filename="{nombre}"'})
            else:
                self.responder(json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if ruta == "/":
            self.path = "/index.html"
        super().do_GET()

    def list_directory(self, path):  # sin listados de carpetas
        self.send_error(404, "No encontrado")
        return None

    def log_message(self, formato, *args):
        print(f"[paneles] {self.client_address[0]} {formato % args}")


def ip_en_la_red() -> str:
    """IP de esta laptop en la red local (no envía nada: solo elige la interfaz de salida)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description="Servidor de los paneles web")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = toda la red (por defecto)")
    ap.add_argument("--puerto", type=int, default=PUERTO)
    args = ap.parse_args()

    servidor = ThreadingHTTPServer((args.host, args.puerto), Manejador)
    print(f"[paneles] Sirviendo {WEB}")
    print(f"[paneles] En esta laptop:  http://localhost:{args.puerto}/")
    ip = ip_en_la_red()
    if args.host == "0.0.0.0" and ip:
        print(f"[paneles] Desde otra laptop: http://{ip}:{args.puerto}/tripulacion.html (solo lectura)")
    print(f"[paneles] Estación: http://localhost:{args.puerto}/estacion.html")
    print("[paneles] Ctrl+C para salir.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[paneles] Saliendo.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
