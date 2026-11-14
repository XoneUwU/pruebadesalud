// Copien este archivo como secrets.h (en la misma carpeta) y pongan sus datos. secrets.h NO se sube a Git.
#pragma once

#define WIFI_SSID "nombre-de-la-red"
#define WIFI_PASS "clave-de-la-red"

// La IP de la laptop de Bri (la que corre Mosquitto). En casa: la de su laptop; en el evento: la de Bri.
#define MQTT_HOST "192.168.1.50"
#define MQTT_PORT 1883
// En el evento: el usuario "sistema" y su clave (mosquitto\crear_usuarios.bat). En casa, vacíos.
#define MQTT_USER ""
#define MQTT_PASS ""
