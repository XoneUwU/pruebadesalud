# Firmware del ESP32 (`firmware\apto_esp32\`)

Lee el pulso, la variabilidad del pulso (HRV, RMSSD de 30 s) y el oxígeno en sangre (SpO2) con el MAX30102, el
movimiento con el MPU6050, y muestra el semáforo en un LED RGB, en la pantalla OLED y con 3 pitidos si es rojo.

| Tema MQTT | Qué |
|---|---|
| publica `apto/{persona}/esp32` (cada 1 s) | `persona`, `sesion`, `pulso_lpm`, `hrv_rmssd_ms`, `spo2`, `dedo`, `movimiento` (g), `calidad` (0 a 1). Sin dedo: pulso, HRV y SpO2 en `null`. Con `MODO_SIMULADO`: `"simulado": true`. Lleva `ts` solo si hay internet (NTP) |
| publica `apto/control/modulos/esp32` | `{"activo": true}` con retain al conectar; Last Will `{"activo": false}` |
| escucha `apto/control/sesion` | persona activa (la estación y el copiloto la publican con retain: el ESP32 la sabe aunque se reinicie) |
| escucha `apto/{persona}/semaforo` | color → LED, OLED y 3 pitidos al pasar a rojo |

`calidad` = latidos aceptados / latidos detectados en los últimos 10 s (se descartan intervalos fuera de 30–200
lpm o con saltos de más del 30 %), a la mitad si hay movimiento (> 0,05 g). El coordinador solo usa lecturas con
dedo y calidad ≥ 0,5. Es un prototipo: el SpO2 de un MAX30102 suelto no es de grado médico.

## Cableado

Placa: **ESP32 Dev Module** (a confirmar con la placa de Danilo). Pines en `config.h`, para poder cambiarlos.

| Componente | Pin del componente | ESP32 |
|---|---|---|
| MAX30102 (0x57) | VIN · GND · SDA · SCL | 3V3 · GND · GPIO 21 · GPIO 22 |
| MPU6050 (0x68) | VCC · GND · SDA · SCL · AD0 | 3V3 · GND · GPIO 21 · GPIO 22 · GND (dirección 0x68) |
| OLED SSD1306 128x64 (0x3C) | VCC · GND · SDA · SCL | 3V3 · GND · GPIO 21 · GPIO 22 |
| LED RGB | R · G · B (cada uno con una resistencia de 220 Ω) | GPIO 25 · GPIO 26 · GPIO 27 |
| LED RGB | común | GND si es de **cátodo común** (por defecto); 3V3 si es de **ánodo común** y `LED_ANODO_COMUN 1` |
| Zumbador activo | + · − | 5V (VIN) · colector de un NPN (2N2222 o BC547) |
| Transistor NPN | base · emisor | GPIO 4 con una resistencia de 1 kΩ · GND (HIGH en GPIO 4 = suena) |

Los tres módulos I2C van en paralelo en el mismo bus (SDA 21, SCL 22). Aliméntenlos con **3V3**, no con 5V.

## Librerías (Gestor de librerías del Arduino IDE)

- **SparkFun MAX3010x Pulse and Proximity Sensor Library** (MAX30102, `checkForBeat`, `spo2_algorithm`)
- **PubSubClient** (Nick O'Leary)
- **ArduinoJson** 7 (Benoît Blanchon)
- **Adafruit SSD1306** y **Adafruit GFX Library** (instala también Adafruit BusIO)

El MPU6050 se lee directo por I2C: no necesita librería.

## Cargarlo

1. Copien `apto_esp32\secrets.ejemplo.h` como `apto_esp32\secrets.h` y pongan el Wi-Fi, la IP de la laptop de Bri
   (la que corre Mosquitto) y, en el evento, el usuario `sistema` y su clave. `secrets.h` no se sube a Git.
2. **Arduino IDE**: Archivo → Preferencias → «URLs adicionales del gestor de placas»:
   `https://espressif.github.io/arduino-esp32/package_esp32_index.json`. Herramientas → Placa → Gestor de placas →
   instalar **esp32** (Espressif). Instalar las librerías de arriba. Abrir `apto_esp32\apto_esp32.ino`, elegir
   **ESP32 Dev Module** y el puerto COM, y **Subir**. Si no sube, mantener apretado BOOT al empezar a subir.
3. **Línea de comandos** (el Arduino IDE trae `arduino-cli.exe` en `resources\app\lib\backend\resources\`):
   ```
   arduino-cli compile --fqbn esp32:esp32:esp32 firmware\apto_esp32
   arduino-cli upload  --fqbn esp32:esp32:esp32 -p COM5 firmware\apto_esp32
   arduino-cli monitor -p COM5 -c baudrate=115200
   ```

## Probarlo

1. **Sin sensores** (solo la placa): en `config.h`, `#define MODO_SIMULADO 1` (o al compilar:
   `--build-property "compiler.cpp.extra_flags=-DMODO_SIMULADO=1"`). Publica datos falsos con `"simulado": true`.
2. En la laptop: `iniciar.bat dev` (o el broker y `python herramientas\escuchar.py`). Deberían ver:
   - `apto/control/modulos/esp32 {"activo": true}` al conectarse, y la estación lo muestra como módulo activo;
   - `apto/bri/esp32` cada segundo (la persona es la de la última sesión de la estación);
   - en la estación, paso 1, pulso, HRV y SpO2 en vivo.
3. Semáforo: `python herramientas\simulador.py --persona bri` y luego `3` (rojo): el LED se pone rojo, la OLED dice
   ROJO y suenan 3 pitidos. `1` verde, `2` amarillo.
4. Con sensores (`MODO_SIMULADO 0`): poner el dedo en el MAX30102 sin apretar; a los pocos segundos aparece el
   pulso, la HRV después de unos 30 s y el SpO2 cada 4 s.

Monitor serie a 115200: dice qué sensores encontró y, cada 5 s, las lecturas y el estado de Wi-Fi y MQTT.
**LED azul** = sin conexión al broker. `MQTT ... estado -2`: no llega a la IP (revisen la IP, la red y el
firewall, puerto 1883); `estado 5`: usuario o clave incorrectos.

Ajustes en `config.h`: `UMBRAL_DEDO` (si no detecta el dedo o lo detecta sin dedo), `BRILLO_LED_SENSOR` (si la
señal satura o es débil), `PERSONA_INICIAL`.
