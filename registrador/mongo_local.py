"""Arranca el MongoDB ya instalado en esta PC como un programa normal: sin servicio y sin administrador.

  python registrador/mongo_local.py

- Datos en datos/mongo (no se sube a Git) y registro en datos/mongo/mongod.log.
- Escucha SOLO en 127.0.0.1, en el puerto de MONGO_URI: nadie de la red puede conectarse.
- Si ese puerto ya está ocupado (por ejemplo, por el servicio de Windows de MongoDB), no arranca otro y avisa.
- Busca mongod en MONGOD_EXE (config.env), en el PATH o en C:\\Program Files\\MongoDB\\Server\\*\\bin.
Ctrl+C lo detiene.
"""
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comun import config  # noqa: E402

CARPETA = config.RAIZ / "datos" / "mongo"


def buscar_mongod() -> str | None:
    if config.get("MONGOD_EXE"):
        return config.get("MONGOD_EXE")
    if shutil.which("mongod"):
        return shutil.which("mongod")
    candidatos = sorted(Path(r"C:\Program Files\MongoDB\Server").glob(r"*\bin\mongod.exe"),
                        key=lambda p: [int(x) if x.isdigit() else x for x in p.parent.parent.name.split(".")])
    return str(candidatos[-1]) if candidatos else None


def puerto_ocupado(puerto: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", puerto)) == 0


def main():
    uri = urlparse(config.get("MONGO_URI", "mongodb://localhost:27017"))
    if uri.hostname not in ("localhost", "127.0.0.1"):
        print(f"[mongo] MONGO_URI apunta a {uri.hostname}, no a esta PC: no arranco nada.")
        return
    puerto = uri.port or 27017
    if puerto_ocupado(puerto):
        print(f"[mongo] Ya hay algo escuchando en el puerto {puerto} (¿el servicio de Windows de MongoDB?).")
        print("[mongo] No arranco otro. Si es el servicio, revisen que su mongod.cfg tenga bindIp: 127.0.0.1.")
        return
    mongod = buscar_mongod()
    if not mongod:
        print("[mongo] No encontré mongod. Instalen MongoDB Community Server (mongodb.com) o pongan su ruta en "
              "MONGOD_EXE dentro de config.env.")
        return
    CARPETA.mkdir(parents=True, exist_ok=True)
    log = CARPETA / "mongod.log"
    print(f"[mongo] {mongod}")
    print(f"[mongo] Escuchando solo en 127.0.0.1:{puerto}. Datos en {CARPETA}. Registro en {log.name}.")
    print("[mongo] Ctrl+C para detenerlo.")
    proceso = subprocess.Popen([mongod, "--dbpath", str(CARPETA), "--bind_ip", "127.0.0.1", "--port", str(puerto),
                                "--logpath", str(log), "--logappend"])
    try:
        codigo = proceso.wait()
    except KeyboardInterrupt:
        print("\n[mongo] Deteniendo MongoDB…")
        codigo = proceso.wait()
    if codigo:
        print(f"[mongo] mongod terminó con código {codigo}. Últimas líneas de {log.name}:")
        if log.exists():
            for linea in log.read_text(encoding="utf-8", errors="replace").splitlines()[-5:]:
                print("   ", linea[:300])


if __name__ == "__main__":
    main()
