"""Cliente MQTT común para todos los módulos.

Uso:
    from comun.mqtt_cliente import ClienteMQTT
    cli = ClienteMQTT("voz")
    cli.conectar()
    cli.publicar("apto/bri/voz", {"f0_media": 180.2})
    cli.suscribir("apto/+/evaluacion", mi_funcion)   # mi_funcion(tema, datos_dict)

Todos los mensajes son JSON y llevan persona, sesion y ts (ver el documento del proyecto).

Cada módulo avisa que está activo: al conectarse publica con retain en apto/control/modulos/{modulo}
{"activo": true}, y deja un Last Will {"activo": false} que el broker publica si el programa se cae.
Al cerrar con cerrar() publica {"activo": false}. La estación de los paneles lo usa para decir
«el módulo X no está abierto». (No se usa apto/estado/{modulo}: coincidiría con apto/+/voz.)
"""
import json
import time
import uuid
from datetime import datetime
from typing import Callable

import paho.mqtt.client as mqtt

from comun import config

PREFIJO = "apto"


def ahora_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def tema_modulo(nombre_modulo: str) -> str:
    """tema_modulo("voz") -> "apto/control/modulos/voz" (cuatro niveles: no coincide con apto/+/voz)."""
    return f"{PREFIJO}/control/modulos/{nombre_modulo}"


def tema(persona: str, tipo: str) -> str:
    """tema("erick", "voz") -> "apto/erick/voz"."""
    return f"{PREFIJO}/{persona}/{tipo}"


class ClienteMQTT:
    def __init__(self, nombre_modulo: str):
        self.nombre = nombre_modulo
        self.host = config.get("MQTT_HOST", "localhost")
        self.port = config.get_int("MQTT_PORT", 1883)
        self._handlers: list[tuple[str, Callable[[str, dict], None]]] = []
        self.conectado = False
        self._c = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{nombre_modulo}-{uuid.uuid4().hex[:6]}",
        )
        usuario = config.get("MQTT_USER")
        if usuario:
            self._c.username_pw_set(usuario, config.get("MQTT_PASS"))
        # Si el programa se cae, el broker publica esto por él (con retain).
        self._c.will_set(tema_modulo(nombre_modulo), self._presencia(False), qos=1, retain=True)
        self._c.on_connect = self._on_connect
        self._c.on_disconnect = self._on_disconnect
        self._c.on_message = self._on_message
        self._c.reconnect_delay_set(min_delay=1, max_delay=10)

    # --- conexión ---
    def conectar(self, espera_s: float = 5.0) -> bool:
        """Conecta y espera hasta espera_s. Devuelve True si quedó conectado."""
        try:
            self._c.connect(self.host, self.port, keepalive=30)
        except OSError as e:
            print(f"[{self.nombre}] No se pudo conectar a MQTT {self.host}:{self.port} ({e}).")
            return False
        self._c.loop_start()
        limite = time.time() + espera_s
        while not self.conectado and time.time() < limite:
            time.sleep(0.05)
        if not self.conectado:
            print(f"[{self.nombre}] MQTT no respondió en {espera_s} s ({self.host}:{self.port}).")
        return self.conectado

    def cerrar(self):
        if self.conectado:  # al cerrar bien no hay Last Will: se avisa a mano
            info = self._c.publish(tema_modulo(self.nombre), self._presencia(False), qos=1, retain=True)
            try:
                info.wait_for_publish(timeout=1.0)
            except (RuntimeError, ValueError):
                pass
        self._c.disconnect()
        self._c.loop_stop()

    def _presencia(self, activo: bool) -> str:
        datos = {"modulo": self.nombre, "activo": activo}
        if activo:
            datos["ts"] = ahora_iso()
        return json.dumps(datos, ensure_ascii=False)

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code.is_failure:
            print(f"[{self.nombre}] MQTT rechazó la conexión: {reason_code} (¿usuario o clave?).")
            return
        self.conectado = True
        print(f"[{self.nombre}] Conectado a MQTT {self.host}:{self.port}")
        client.publish(tema_modulo(self.nombre), self._presencia(True), qos=1, retain=True)
        for patron, _ in self._handlers:  # re-suscribir tras reconexión
            client.subscribe(patron, qos=1)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.conectado = False
        if reason_code != 0:
            print(f"[{self.nombre}] Se perdió la conexión MQTT; reintentando...")

    def _on_message(self, client, userdata, msg):
        try:
            datos = json.loads(msg.payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            print(f"[{self.nombre}] Mensaje no JSON en {msg.topic}; se ignora.")
            return
        for patron, funcion in self._handlers:
            if mqtt.topic_matches_sub(patron, msg.topic):
                try:
                    funcion(msg.topic, datos)
                except Exception as e:  # un error en un handler no debe tumbar el módulo
                    print(f"[{self.nombre}] Error procesando {msg.topic}: {e}")

    # --- publicar / suscribir ---
    def publicar(self, tema_mqtt: str, datos: dict, retener: bool = False) -> bool:
        datos = dict(datos)
        datos.setdefault("ts", ahora_iso())
        datos.setdefault("fuente", self.nombre)
        if not self.conectado:
            print(f"[{self.nombre}] (sin MQTT) {tema_mqtt}: {json.dumps(datos, ensure_ascii=False)}")
            return False
        info = self._c.publish(tema_mqtt, json.dumps(datos, ensure_ascii=False), qos=1, retain=retener)
        return info.rc == mqtt.MQTT_ERR_SUCCESS

    def suscribir(self, patron: str, funcion: Callable[[str, dict], None]):
        self._handlers.append((patron, funcion))
        if self.conectado:
            self._c.subscribe(patron, qos=1)


def persona_de_tema(tema_mqtt: str) -> str:
    """'apto/erick/evaluacion' -> 'erick'."""
    partes = tema_mqtt.split("/")
    return partes[1] if len(partes) >= 3 else ""
