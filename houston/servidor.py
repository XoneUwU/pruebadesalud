"""Servidor web de Houston (control de misión en Tierra): muestra la réplica que llena enlace.py. Solo lee.

  python houston/servidor.py                 http://localhost:8090 (y http://IP-de-esta-laptop:8090 desde la red)
  python houston/servidor.py --host 127.0.0.1    solo esta laptop

MVC: modelo.py (consulta la réplica), controlador.py (rutas y respuestas) y web/ (la vista: HTML, CSS y JS sin
frameworks ni internet). No se conecta al broker MQTT: Houston solo ve lo que ya bajó por el enlace.
"""
import argparse
import socket
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from comun import config  # noqa: E402
from controlador import WEB, Manejador  # noqa: E402


def ip_en_la_red() -> str:
    """IP de esta laptop en la red local (no envía nada: solo elige la interfaz de salida)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description="Servidor web de Houston")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = toda la red (por defecto)")
    ap.add_argument("--puerto", type=int, default=config.get_int("HOUSTON_PUERTO", 8090))
    args = ap.parse_args()

    servidor = ThreadingHTTPServer((args.host, args.puerto), Manejador)
    print(f"[houston] Sirviendo {WEB}")
    print(f"[houston] En esta laptop:  http://localhost:{args.puerto}/")
    ip = ip_en_la_red()
    if args.host == "0.0.0.0" and ip:
        print(f"[houston] Desde otra laptop: http://{ip}:{args.puerto}/")
    print("[houston] Ctrl+C para salir.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n[houston] Saliendo.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
