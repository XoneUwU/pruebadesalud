"""Receptor de Houston: se suscribe a Mosquitto (apto/#) y guarda en la base de Houston lo que baja a Tierra.

  python houston/receptor.py                retraso HOUSTON_RETRASO_S (por defecto RETRASO_TIERRA_S)
  python houston/receptor.py --retraso 0    sin retraso (para probar)

- Solo escucha: se conecta con el usuario de solo lectura (MQTT_USER_LECTURA, el «equipo» del modo evento; si está
  vacío, con MQTT_USER) y no publica nada, ni siquiera su presencia: la estación no lo ve como un módulo de la nave.
- No es una copia exacta: guarda solo los tipos de modelo.TIPOS (datos, evaluaciones, copiloto y sesiones; no las
  órdenes ni los estados de los módulos). Cada documento tiene la forma del registrador de la nave
  ({recibido, tema, persona, tipo, simulado, reproducido, datos}) y además `llego_tierra`.
- Retraso de la comunicación: cada mensaje se guarda al llegar, con `llego_tierra` = recibido + retraso. Houston
  (modelo.py) solo muestra lo que ya «llegó» (`llego_tierra` <= ahora). Así un reinicio no pierde lo que viene en camino.
- Los mensajes retenidos que el broker entrega al conectarse (la última evaluación de cada uno, la sesión) se guardan
  una sola vez: si ya están (mismo tema, sesión y ts), no se repiten.
- Cada 2 s escribe su estado en la colección "enlace" (documento "estado"): si está conectado, cuántos guardó y la hora.
Ctrl+C lo detiene.
"""
import argparse
import json
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "registrador"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from almacen import persona_y_tipo  # noqa: E402

from comun import config  # noqa: E402
from modelo import COLECCION, COLECCION_ENLACE, TIPOS, retraso_s  # noqa: E402

CADA_S = 2


def documento(tema: str, datos, retraso: float, ahora: datetime | None = None) -> dict | None:
    """Mensaje MQTT -> documento de Houston, o None si ese tipo no baja a Tierra."""
    if not isinstance(datos, dict):
        datos = {"valor": datos}
    persona, tipo = persona_y_tipo(tema, datos)
    if tipo not in TIPOS:
        return None
    ahora = ahora or datetime.now(timezone.utc)
    return {
        "recibido": ahora, "llego_tierra": ahora + timedelta(seconds=retraso), "tema": tema,
        "persona": persona, "tipo": tipo, "simulado": bool(datos.get("simulado")),
        "reproducido": bool(datos.get("reproducido")), "datos": datos,
    }


def clave_retenido(doc: dict) -> dict:
    """Con qué se reconoce un mensaje retenido que ya se guardó (el broker lo vuelve a dar en cada conexión)."""
    datos = doc["datos"]
    return {"tema": doc["tema"], "datos.sesion": datos.get("sesion"), "datos.ts": datos.get("ts")}


class Receptor:
    def __init__(self, coleccion, estado, retraso: float):
        self.col = coleccion
        self.estado = estado
        self.retraso = retraso
        self.guardados = 0
        self.conectado = False
        self.error = ""
        self._lock = threading.Lock()

    def guardar(self, tema: str, datos, retenido: bool = False) -> bool:
        doc = documento(tema, datos, self.retraso)
        if doc is None:
            return False
        if retenido:  # lo que ya estaba antes de conectarse: ya llegó a Tierra (si no estaba guardado)
            doc["llego_tierra"] = doc["recibido"]
            r = self.col.update_one(clave_retenido(doc), {"$setOnInsert": doc}, upsert=True)
            nuevo = r.upserted_id is not None
        else:
            self.col.insert_one(doc)
            nuevo = True
        if nuevo:
            with self._lock:
                self.guardados += 1
        return nuevo

    def latido(self):
        self.estado.update_one({"_id": "estado"}, {"$set": {
            "actualizado": datetime.now(timezone.utc), "conectado": self.conectado, "guardados": self.guardados,
            "retraso_s": self.retraso, "error": self.error,
        }}, upsert=True)


def cliente_mqtt(receptor: Receptor):
    import paho.mqtt.client as mqtt

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"houston-{uuid.uuid4().hex[:6]}")
    usuario, clave = config.get("MQTT_USER_LECTURA"), config.get("MQTT_PASS_LECTURA")
    if not usuario:
        usuario, clave = config.get("MQTT_USER"), config.get("MQTT_PASS")
    if usuario:
        c.username_pw_set(usuario, clave)

    def al_conectar(client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            receptor.conectado = False
            receptor.error = f"Mosquitto rechazó la conexión ({reason_code}): revisen usuario y clave"
            print(f"[houston] {receptor.error}")
            return
        receptor.conectado, receptor.error = True, ""
        print(f"[houston] Conectado a Mosquitto {config.get('MQTT_HOST', 'localhost')}; escuchando apto/#")
        client.subscribe("apto/#", qos=1)

    def al_desconectar(client, userdata, flags, reason_code, properties):
        receptor.conectado = False
        receptor.error = "Sin conexión con Mosquitto"
        print("[houston] Se perdió la conexión con Mosquitto; reintentando…")

    def al_recibir(client, userdata, msg):
        try:
            datos = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        try:
            receptor.guardar(msg.topic, datos, msg.retain)
        except Exception as e:  # Mongo caído: se pierde ese mensaje, pero el receptor sigue
            receptor.error = f"No se pudo guardar en MongoDB ({type(e).__name__})"
            print(f"[houston] {receptor.error}: {msg.topic}")

    c.on_connect, c.on_disconnect, c.on_message = al_conectar, al_desconectar, al_recibir
    c.reconnect_delay_set(min_delay=1, max_delay=10)
    return c


def main():
    ap = argparse.ArgumentParser(description="Receptor de Houston: Mosquitto -> MongoDB de Houston")
    ap.add_argument("--retraso", type=lambda s: float(s.replace(",", ".")), default=None,
                    help="segundos de retraso, con decimales (por defecto HOUSTON_RETRASO_S)")
    args = ap.parse_args()

    from pymongo import MongoClient

    retraso = retraso_s() if args.retraso is None else max(0, args.retraso)
    base = MongoClient(config.get("HOUSTON_MONGO_URI", "mongodb://localhost:27017"),
                       serverSelectionTimeoutMS=2000, tz_aware=True)[config.get("HOUSTON_MONGO_DB", "houston")]
    receptor = Receptor(base[COLECCION], base[COLECCION_ENLACE], retraso)
    host, puerto = config.get("MQTT_HOST", "localhost"), config.get_int("MQTT_PORT", 1883)
    print(f"[houston] Mosquitto {host}:{puerto} -> MongoDB base {base.name}. Retraso {retraso} s. Ctrl+C para salir.")

    indices = False
    cliente = cliente_mqtt(receptor)
    cliente.connect_async(host, puerto, keepalive=30)
    cliente.loop_start()
    ultimo_resumen = time.time()
    try:
        while True:
            try:
                if not indices:
                    base[COLECCION].create_index([("persona", 1), ("tipo", 1), ("recibido", 1)], name="persona_tipo_recibido")
                    base[COLECCION].create_index("llego_tierra", name="llego_tierra")
                    base[COLECCION].create_index("datos.sesion", name="sesion")
                    indices = True
                receptor.latido()
            except Exception as e:
                print(f"[houston] MongoDB de Houston no responde ({type(e).__name__}); reintento.")
            if not receptor.conectado and receptor.error == "":
                receptor.error = f"Conectando a Mosquitto {host}:{puerto}…"
            if time.time() - ultimo_resumen >= 60:
                ultimo_resumen = time.time()
                print(f"[houston] Guardados: {receptor.guardados} | Mosquitto {'bien' if receptor.conectado else 'sin conexión'}")
            time.sleep(CADA_S)
    except KeyboardInterrupt:
        print("\n[houston] Saliendo.")
    finally:
        cliente.loop_stop()
        cliente.disconnect()


if __name__ == "__main__":
    main()
