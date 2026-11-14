"""Servidor de los paneles web: sirve paneles/web/ y genera /config.js desde config.env.

  python paneles/servidor.py                 http://localhost:8080 en esta laptop
                                             http://IP-de-esta-laptop:8080 desde las demás
  python paneles/servidor.py --host 127.0.0.1    solo esta laptop (para probar)

Las páginas se conectan al broker por WebSocket (MQTT_WS_PORT, 9001) en el mismo host desde el que se
abrieron. /config.js lleva las credenciales: si la página se abre en esta misma laptop (localhost), las
de MQTT_USER, que puede publicar; si se abre desde otra laptop, las de solo lectura (MQTT_USER_LECTURA).
Solo usa la biblioteca estándar. Si cambian config.env, reinicien el servidor.
"""
import argparse
import ast
import json
import socket
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from comun import config  # noqa: E402

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
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self):
        ruta = self.path.split("?", 1)[0].split("#", 1)[0]
        if ruta == "/config.js":
            cuerpo = config_js(es_local(self.client_address[0]))
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)
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
    print("[paneles] Ctrl+C para salir.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[paneles] Saliendo.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
