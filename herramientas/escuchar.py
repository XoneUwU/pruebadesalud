"""Muestra en pantalla todos los mensajes MQTT del proyecto (como mosquitto_sub).

  python herramientas/escuchar.py                 todos los temas apto/#
  python herramientas/escuchar.py apto/+/voz      solo un patrón
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from comun.mqtt_cliente import ClienteMQTT


def main():
    patron = sys.argv[1] if len(sys.argv) > 1 else "apto/#"
    cli = ClienteMQTT("escuchar")
    if not cli.conectar():
        return
    cli.suscribir(patron, lambda t, d: print(f"\n{t}\n{json.dumps(d, indent=2, ensure_ascii=False)}"))
    print(f"Escuchando {patron} (Ctrl+C para salir)")
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        cli.cerrar()


if __name__ == "__main__":
    main()
