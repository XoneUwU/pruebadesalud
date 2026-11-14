"""Registrador: guarda en MongoDB cada mensaje de apto/# (colección "mensajes").

  python registrador/registrador.py

- Índices por (persona, tipo, recibido) y por tipo.
- Si MongoDB no responde, no se pierde nada: los mensajes van a datos/pendientes_mongo.jsonl y se suben
  solos cuando Mongo vuelve (cada línea lleva su _id, así un reintento nunca duplica).
- Los mensajes retenidos que el broker entrega al conectarse no se guardan otra vez: ya se guardaron
  cuando se publicaron.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from almacen import PENDIENTES, a_linea, conectar, crear_indices, de_linea, documento  # noqa: E402

from comun import config  # noqa: E402
from comun.mqtt_cliente import ClienteMQTT  # noqa: E402

CADA_S = 5        # cada cuánto se intenta subir lo pendiente
RESUMEN_S = 60    # cada cuánto se muestra el resumen


class Registrador:
    """Guarda en la colección, o en el archivo de pendientes si Mongo no responde."""

    def __init__(self, coleccion, ping, pendientes: Path = PENDIENTES):
        self.col = coleccion
        self.ping = ping                  # función que lanza una excepción si Mongo no responde
        self.pendientes = pendientes
        self.caido = False                # mientras Mongo no responde, todo va directo al archivo
        self.guardados = 0
        self.al_archivo = 0
        self.subidos = 0
        self._lock = threading.Lock()

    def guardar(self, tema: str, datos, retenido: bool = False):
        if retenido:
            return
        doc = documento(tema, datos)
        from pymongo.errors import PyMongoError
        with self._lock:
            if not self.caido:
                try:
                    self.col.insert_one(doc)
                    self.guardados += 1
                    return
                except PyMongoError as e:
                    self.caido = True  # el doc conserva el _id que le puso insert_one: si alcanzó a guardarse, no se duplica
                    print(f"[registrador] MongoDB no responde ({type(e).__name__}): guardo en {self.pendientes.name}")
            self.pendientes.parent.mkdir(parents=True, exist_ok=True)
            with open(self.pendientes, "a", encoding="utf-8") as f:
                f.write(a_linea(doc) + "\n")
            self.al_archivo += 1

    def _responde(self) -> bool:
        from pymongo.errors import PyMongoError
        try:
            self.ping()
            return True
        except PyMongoError:
            return False

    def subir_pendientes(self) -> int:
        """Si hay pendientes y Mongo responde, los sube y borra el archivo. Devuelve cuántos subió."""
        from pymongo.errors import BulkWriteError, PyMongoError
        hay = self.pendientes.exists() and self.pendientes.stat().st_size > 0
        if not hay and not self.caido:
            return 0
        if not self._responde():  # fuera del candado: el ping puede tardar
            return 0
        with self._lock:
            if not self.pendientes.exists():
                self.caido = False
                return 0
            docs = [de_linea(linea) for linea in self.pendientes.read_text(encoding="utf-8").splitlines() if linea.strip()]
            try:
                if docs:
                    self.col.insert_many(docs, ordered=False)
            except BulkWriteError as e:  # los que ya estaban (mismo _id) no cuentan como error
                otros = [w for w in e.details.get("writeErrors", []) if w.get("code") != 11000]
                if otros:
                    print(f"[registrador] No se pudieron subir {len(otros)} pendientes: {otros[0].get('errmsg')}")
                    return 0
            except PyMongoError as e:
                print(f"[registrador] Mongo volvió a fallar al subir pendientes ({type(e).__name__}).")
                return 0
            self.pendientes.unlink()
            self.caido = False
            self.subidos += len(docs)
            print(f"[registrador] MongoDB responde: subí {len(docs)} mensajes pendientes.")
            return len(docs)


def main():
    cliente, col = conectar()
    reg = Registrador(col, lambda: cliente.admin.command("ping"))
    indices = False
    try:
        reg.ping()
        crear_indices(col)
        indices = True
        print(f"[registrador] MongoDB: {config.get('MONGO_URI', 'mongodb://localhost:27017')} "
              f"base {config.get('MONGO_DB', 'apto_hoy')}, colección {col.name}")
    except Exception as e:
        print(f"[registrador] MongoDB no responde todavía ({type(e).__name__}): los mensajes irán a "
              f"{PENDIENTES} hasta que vuelva.")
        reg.caido = True

    cli = ClienteMQTT("registrador")
    if not cli.conectar():
        print("El registrador necesita MQTT. Revisen que Mosquitto esté corriendo.")
        return
    cli.suscribir("apto/#", reg.guardar, con_retain=True)
    print("[registrador] Guardando apto/# (Ctrl+C para salir).")

    ultimo = time.time()
    try:
        while True:
            time.sleep(CADA_S)
            reg.subir_pendientes()
            if not indices and not reg.caido:
                try:
                    crear_indices(col)
                    indices = True
                except Exception:
                    pass
            if time.time() - ultimo >= RESUMEN_S:
                ultimo = time.time()
                print(f"[registrador] En Mongo: {reg.guardados + reg.subidos} | en archivo ahora: "
                      f"{'sí' if PENDIENTES.exists() else 'no'} | Mongo {'caído' if reg.caido else 'bien'}")
    except KeyboardInterrupt:
        print("\n[registrador] Saliendo.")
    finally:
        cli.cerrar()


if __name__ == "__main__":
    main()
