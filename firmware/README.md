# Firmware del ESP32 (`firmware\apto_esp32\`)

Lee el pulso, la variabilidad del pulso (HRV, RMSSD de 30 s) y el oxígeno en sangre (SpO2) con el MAX30102, el
movimiento con el MPU6050, la activación muscular con el AD8232 (prototipo), y muestra el semáforo en un LED RGB, en la pantalla OLED y con 3 pitidos si es rojo. Con Wi-Fi sigue la evaluación de
la estación con una secuencia guiada en la OLED (ver la sección 9 del README principal).

| Tema MQTT | Qué |
|---|---|
| publica `apto/{persona}/esp32` (cada 1 s) | `persona`, `sesion`, `pulso_lpm`, `hrv_rmssd_ms`, `spo2`, `dedo`, `movimiento` (g), `calidad` (0 a 1), `electrodos`, `musculo_rms_mv`, `musculo_pico_mv` (ver «Activación muscular»). Sin dedo: pulso, HRV y SpO2 en `null`. Con `MODO_SIMULADO`: `"simulado": true`. Lleva `ts` solo si hay internet (NTP) |
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
| LED RGB | R · G · B, cada canal con una resistencia de 220 Ω | GPIO 25 · GPIO 26 · GPIO 27 |
| LED RGB | común (pata larga) | GND si es de **cátodo común** (por defecto); 3V3 si es de **ánodo común** y `LED_ANODO_COMUN 1` |
| Zumbador (activo o pasivo) | + · − | 5V (VIN) · colector de un NPN (2N2222 o BC547) |
| Transistor NPN | base · emisor | GPIO 4 con una resistencia de 1 kΩ · GND (HIGH en GPIO 4 = suena) |
| AD8232 | 3.3v · GND · OUTPUT · LO− · LO+ · SDN | 3V3 · GND · GPIO 34 · GPIO 35 · GPIO 32 · sin conectar |

Los tres módulos I2C van en paralelo en el mismo bus (SDA 21, SCL 22). Aliméntenlos con **3V3**, no con 5V. El
AD8232 también va a **3V3**: con 5 V su salida pasaría de lo que aguanta el ADC del ESP32.

## Librerías (Gestor de librerías del Arduino IDE)

- **SparkFun MAX3010x Pulse and Proximity Sensor Library** (MAX30102 y `spo2_algorithm`; los latidos los detecta el propio firmware)
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

## Activación muscular (AD8232, prototipo)

El AD8232 es un chip de ECG: filtra de 0,5 a 40 Hz, así que sirve para ver **cuándo y cuánto** se contrae el
músculo, no es una electromiografía real. Electrodos en el antebrazo: RA y LA sobre el músculo, RL en el hueso
del codo.

| Campo | Qué es |
|---|---|
| `electrodos` | `true` si los tres electrodos estuvieron pegados más de la mitad del último segundo (salidas LO+ y LO−) |
| `musculo_rms_mv` | RMS de la señal en el último segundo: cuánta actividad hubo |
| `musculo_pico_mv` | pico de la envolvente (suavizada ~100 ms) en el último segundo: la contracción más fuerte |
| `musculo_orden` | solo en la prueba guiada (`"fase": "musculo"`): `preparate`, `aprieta`, `espera` o `descansa`. La estación la muestra y el coordinador separa lo medido al apretar y en reposo |

- **Por ahora los valores publicados son fingidos** (`MUSCULO_FINGIDO 1` en `config.h`) y el mensaje lleva
  `"musculo_simulado": true`: suben mientras la prueba guiada dice APRIETA. `electrodos` sí es real. En la prueba
  del 15/11 la señal real no servía: con la laptop enchufada al cargador, el 72 % era zumbido de 50 Hz. Los valores
  reales siguen en el monitor serie (`real rms=… pico=…`) para seguir con eso. Con `MUSCULO_FINGIDO 0` se publican
  los reales.
- **Prueba guiada (35 s)**: con red, después de los 30 s del dedo la OLED sigue con el músculo (`"fase": "musculo"`,
  con `quedan_s`). `medicion_lista` llega al final de las dos. Cada orden tiene una pausa de 2 s para reaccionar:
  PREPARATE 5 s → APRIETA 5 → ESPERA 2 → DESCANSA 6 → ESPERA 2 → APRIETA 5 → ESPERA 2 → DESCANSA 8. Dos pitidos =
  aprieta, uno = descansa. Abajo, la OLED avisa si un electrodo pierde contacto (LO+ = LA amarillo, LO− = RA rojo,
  los dos = revisa RL verde) o si la salida está en el tope. Sin electrodos en los primeros 4 s, se omite. Sin red,
  igual, y después el resultado del pulso. `MUSCULO_EN_EVALUACION 0` la quita.
- **Solo el AD8232**: `-DPRUEBA_MUSCULO=1` repite la prueba guiada sin Wi-Fi ni pulso, con los valores reales, y
  manda una línea por segundo por el monitor serie. Con `-DCRUDO_MUSCULO=1`, además, cada lectura (500/s).
- Filtros: pasa altos de 10 Hz, notch de 50 y 100 Hz (`MUSCULO_RED_HZ`) y pasa bajos de 45 Hz (los armónicos de
  150, 200 y 250 Hz eran casi la mitad de lo que quedaba). Con la captura del 15/11, el 92 % de la señal filtrada
  queda entre 10 y 45 Hz. LO+ o LO− cuentan como despegado solo si
  quedan en alto 50 ms seguidos: con ruido dan pulsos cortos aunque los electrodos estén bien.
- Los valores están en **mV a la salida del AD8232**, que amplifica mucho la señal: no son los microvoltios reales
  del músculo. Se leen con `analogReadMilliVolts` (con la calibración de fábrica de la placa).
- Sin electrodos: `electrodos: false` y los dos valores en `null`. Recién pegados: `electrodos: true` y los valores en
  `null` durante el primer segundo, mientras la salida del AD8232 se acomoda (`MUSCULO_ASENTAR_MS`).
- La lectura va en una tarea de FreeRTOS aparte, 500 veces por segundo exactas: la OLED, el MAX30102 o un broker que
  no responde ya no la frenan.
- Con `MODO_SIMULADO` publica valores falsos: `electrodos: true`, unos 20 mV en reposo y unos 240 mV mientras la
  prueba guiada dice APRIETA. Sirve para armar la estación sin el AD8232.

Para revisar el cableado, el monitor serie muestra cada 5 s una línea así:

```
[esp32] musculo electrodos=0 real rms=nan pico=nan | publicado rms=nan pico=nan mV lecturas/s=500 lo+=1 lo-=1 salida=2618 mV
```

`lecturas/s` debe dar unas 500. `lo+` y `lo-` en 1 = algún electrodo despegado: si siguen en 1 con los tres pegados,
revisen el cable de los electrodos y los pines 32 y 35. Con los electrodos puestos y el brazo quieto, `salida` debe
quedar cerca de 1650 mV (la mitad de 3,3 V).

**Ver la señal**: compilar con `--build-property "compiler.cpp.extra_flags=-DDEPURAR_MUSCULO=1"` y abrir el Serial
Plotter del Arduino IDE (115200). Muestra la señal y su envolvente en mV, 100 veces por segundo. **Con electrodos
puestos, la laptop va desenchufada del cargador**, para que no haya un camino a la red eléctrica a través del cuerpo
(y además hay menos ruido de 50 Hz).

## Medición guiada sin red (modo local)

Con `WIFI_SSID ""` en `secrets.h` el ESP32 no usa Wi-Fi ni MQTT y hace una medición guiada él solo:

1. OLED «Coloca tu dedo». Al poner el dedo: cuenta 3-2-1 (pitido corto en cada número).
2. Mide `MEDICION_S` (30 s, la ventana de la HRV) con cuenta regresiva, pulso en vivo y el **LED en azul**. Si se retira
   el dedo: «Dedo retirado: repite».
3. Resultado (mediana del pulso con calidad ≥ 0,5; mismas reglas que el coordinador sin línea base):

| Resultado | Cuándo | LED | Zumbador |
|---|---|---|---|
| VERDE | pulso 50–99 | verde | 1 pitido corto |
| AMARILLO | pulso 100–119 («Pulso en reposo alto») o 40–49 («Pulso bajo») | amarillo | 1 pitido |
| ROJO | pulso ≥ 120, o < 40 («Pulso muy bajo») | rojo | 3 pitidos |
| REPITE | menos de 10 s de señal buena | azul parpadeando | 2 pitidos largos |

El SpO2 < 92 solo agrega «Oxigeno bajo» en la OLED, sin cambiar el color. La HRV se muestra pero no se
juzga sin línea base. Para otra medición: retirar el dedo y volver a ponerlo. Probar los colores sin sensor:
`--build-property "compiler.cpp.extra_flags=-DMODO_SIMULADO=1 -DPULSO_FORZADO=130"`.

Los latidos los detecta el propio firmware (`detectarLatido`): `checkForBeat` de SparkFun descartaba los latidos
con más de 1000 cuentas de pico a pico y este sensor da 3000–13000. Para capturar la señal cruda (IR y rojo a
100 muestras/s por el monitor serie): `-DDEPURAR_IR=1`.

El zumbador suena con un tono de 2 kHz (`TONO_ZUMBADOR_HZ` en `config.h`): así suena tanto un zumbador pasivo
como uno activo. Con `0`, HIGH fijo (solo activo).

Monitor serie a 115200: dice qué sensores encontró y, cada 5 s, las lecturas y el estado de Wi-Fi y MQTT.
**LED azul fijo** = evaluación en curso o sin conexión al broker (nunca se encienden los tres canales a la vez). `MQTT ... estado -2`: no llega a la IP (revisen la IP, la red y el
firewall, puerto 1883); `estado 5`: usuario o clave incorrectos.

Ajustes en `config.h`: `UMBRAL_DEDO` (si no detecta el dedo o lo detecta sin dedo), `BRILLO_LED_SENSOR` (si la
señal satura o es débil), `PERSONA_INICIAL`.
