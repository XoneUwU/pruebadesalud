"""Controlador de Houston: recibe cada petición, le pide los datos al modelo y responde con la vista o con JSON.

  GET /                                   la vista (web/index.html)
  GET /api/tablero.json                   última evaluación por tripulante, últimas evaluaciones, copiloto y enlace
  GET /api/evaluaciones.json?dias=7&persona=bri   una fila por evaluación (dias=0 o sin dias = todo)
  GET /api/evaluaciones.csv?dias=7&persona=bri    lo mismo en CSV
  GET /api/sesion.json?sesion=20261113-193005-bri  los mensajes de una sesión (el ESP32, resumido)

La vista usa el diseño de la estación sin copiarlo: nocturne.css, app.css, plantilla.js, logo.js, fondo.js, los íconos
Phosphor y la fuente Inter se sirven desde paneles/web (lista cerrada en COMPARTIDOS).

Solo GET: Houston no cambia nada. Sin listados de carpetas ni archivos fuera de web/ y de esa lista.
"""
import json
import posixpath
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import modelo

WEB = Path(__file__).resolve().parent / "web"
PANELES_WEB = Path(__file__).resolve().parent.parent / "paneles" / "web"
COMPARTIDOS = {"nocturne.css", "app.css", "plantilla.js", "logo.js", "fondo.js"}
CARPETAS_COMPARTIDAS = ("vendor/phosphor/", "vendor/inter/")


def compartido(ruta_url: str) -> Path | None:
    """Ruta pedida -> archivo de paneles/web si es una pieza del diseño compartida; si no, None."""
    ruta = posixpath.normpath(unquote(ruta_url)).lstrip("/")
    if ".." in ruta.split("/"):
        return None
    if ruta in COMPARTIDOS or (ruta.startswith(CARPETAS_COMPARTIDAS) and ruta.count("/") == 2):
        archivo = PANELES_WEB / ruta
        return archivo if archivo.is_file() else None
    return None


def _persona(texto: str) -> str:
    return "".join(c for c in (texto or "").lower() if c.isalnum())


def _dias(texto: str) -> int:
    try:
        return max(0, int(texto or 0))
    except ValueError:
        return 0


# Cada ruta: función (parámetros) -> (cuerpo, tipo, cabeceras extra)
def tablero(q):
    return _json(modelo.tablero())


def evaluaciones(q):
    return _json(modelo.evaluaciones(_dias(q.get("dias")), _persona(q.get("persona"))))


def evaluaciones_csv(q):
    persona, dias = _persona(q.get("persona")), _dias(q.get("dias"))
    datos = modelo.evaluaciones(dias, persona)
    texto = modelo.a_csv(datos["filas"]) if datos.get("disponible") else f"# {datos.get('motivo')}\r\n"
    nombre = f"houston-{persona or 'tripulacion'}-{dias or 'todo'}.csv"
    return texto.encode("utf-8-sig"), "text/csv; charset=utf-8", {"Content-Disposition": f'attachment; filename="{nombre}"'}


def sesion(q):
    return _json(modelo.sesion((q.get("sesion") or "")[:80]))


def _json(datos):
    return json.dumps(datos, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", {}


RUTAS = {
    "/api/tablero.json": tablero,
    "/api/evaluaciones.json": evaluaciones,
    "/api/evaluaciones.csv": evaluaciones_csv,
    "/api/sesion.json": sesion,
}


class Manejador(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".woff2": "font/woff2",
    }

    def end_headers(self):
        # Archivos de la vista: el navegador revisa siempre si cambiaron (Last-Modified), así al actualizar Houston
        # nadie se queda con un CSS o JS viejo mezclado con uno nuevo. La API ya va con no-store.
        if not self.path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def translate_path(self, path):
        archivo = compartido(urlsplit(path).path)
        return str(archivo) if archivo else super().translate_path(path)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def responder(self, cuerpo: bytes, tipo: str, extra: dict | None = None):
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(cuerpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        partes = urlsplit(self.path)
        accion = RUTAS.get(partes.path)
        if accion:
            q = {k: v[-1] for k, v in parse_qs(partes.query).items()}
            self.responder(*accion(q))
            return
        if partes.path.startswith("/api/"):
            self.send_error(404, "No encontrado")
            return
        if partes.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def list_directory(self, path):  # sin listados de carpetas
        self.send_error(404, "No encontrado")
        return None

    def log_message(self, formato, *args):
        print(f"[houston] {self.client_address[0]} {formato % args}")
