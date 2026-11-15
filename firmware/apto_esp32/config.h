// Configuración del ESP32 de «¿Está apto hoy?»: pines y opciones. Las claves van en secrets.h.
#pragma once

// ---------------------------------------------------------------- modo de prueba
// 1 = publica datos falsos sin sensores (prueba todo el camino sin hardware; los mensajes llevan "simulado": true).
// También se puede activar al compilar: arduino-cli compile ... --build-property "compiler.cpp.extra_flags=-DMODO_SIMULADO=1"
#ifndef MODO_SIMULADO
#define MODO_SIMULADO 0
#endif

// ---------------------------------------------------------------- pines (ESP32 Dev Module, a confirmar con la placa)
#define PIN_SDA 21             // I2C: MAX30102 (0x57), MPU6050 (0x68) y OLED SSD1306 (0x3C)
#define PIN_SCL 22
#define PIN_LED_R 25           // LED RGB: cada canal con su resistencia de 220 Ω. Nunca se encienden los tres a la vez:
#define PIN_LED_G 26           // verde = G, amarillo = R + G, rojo = R; azul fijo = midiendo o sin broker;
#define PIN_LED_B 27           // azul parpadeando = repite
#define LED_ANODO_COMUN 0      // 0 = cátodo común (el común a GND, HIGH enciende); 1 = ánodo común (común a 3V3, LOW enciende)
#define PIN_ZUMBADOR 4         // zumbador a través de un transistor NPN (base con 1 kΩ)
#define TONO_ZUMBADOR_HZ 2000  // tono de 2 kHz: suena con zumbador pasivo o activo; 0 = HIGH fijo (solo activo)

// ---------------------------------------------------------------- direcciones I2C
#define DIR_MPU6050 0x68
#define DIR_OLED 0x3C          // el MAX30102 (0x57) lo maneja la librería de SparkFun

// ---------------------------------------------------------------- persona y tiempos
#define PERSONA_INICIAL "danilo"  // hasta que llegue apto/control/sesion (la estación la publica con retain)
#define CADA_PUBLICAR_MS 1000  // apto/{persona}/esp32 cada 1 s
#define CADA_PANTALLA_MS 200
#define MEDICION_S 30          // medición guiada: 30 s = la ventana de la HRV (RMSSD); mínimo para una estimación ultracorta
#define CADA_WIFI_MS 10000     // reintento de Wi-Fi (sin bloquear)
#define CADA_MQTT_MS 5000      // reintento de MQTT (bloquea como máximo MQTT_ESPERA_S)
#define MQTT_ESPERA_S 2

// ---------------------------------------------------------------- MAX30102
#define UMBRAL_DEDO 50000      // IR por encima de esto = hay un dedo (valor del ejemplo de SparkFun)
#define BRILLO_LED_SENSOR 60   // 0 a 255 (corriente de los LED del MAX30102)
#define VENTANA_HRV_MS 30000   // RMSSD con los intervalos entre latidos de los últimos 30 s
#define CADA_SPO2_MS 4000      // SpO2 con spo2_algorithm: 100 muestras a 25 Hz = 4 s

// ---------------------------------------------------------------- MPU6050
#define CADA_MPU_MS 20         // 50 lecturas por segundo; movimiento = desviación de |aceleración| en 1 s
#define UMBRAL_MOVIMIENTO 0.05 // g; con más movimiento la calidad del pulso baja a la mitad

// ---------------------------------------------------------------- AD8232: activación muscular (prototipo)
// El AD8232 es un chip de ECG (filtra de 0,5 a 40 Hz): sirve para ver CUÁNDO y CUÁNTO se contrae el músculo, no es
// una electromiografía real. Electrodos en el antebrazo (RA y LA sobre el músculo, RL en el hueso del codo).
#define PIN_MUSCULO 34         // OUTPUT del AD8232 (ADC1: funciona con Wi-Fi). 3V3, nunca 5 V
#define PIN_LO_MENOS 35        // LO-: en alto = electrodo despegado (GPIO 35 no tiene pull-up interno)
#define PIN_LO_MAS 32          // LO+: en alto = electrodo despegado (con pull-up: sin el módulo también da «despegado»)
#define MUSCULO_CADA_MS 2      // 500 lecturas por segundo, en una tarea aparte (la OLED y el MQTT no la frenan)
#define MUSCULO_ENVOLVENTE 0.02f  // suavizado de |señal| (~100 ms a 500/s): la «fuerza» de la contracción
#define MUSCULO_ASENTAR_MS 1000   // al pegar los electrodos, 1 s sin contar: la salida del AD8232 se está acomodando
#define MUSCULO_DESPEGADO_MS 50   // LO+ o LO- en alto al menos 50 ms seguidos = despegado (pulsos más cortos: ruido)
#define MUSCULO_TOPE_MV 3050     // salida >= esto o <= 100 mV: el AD8232 está en el tope (saturado), no hay señal útil
#define MUSCULO_RED_HZ 50         // frecuencia de la red eléctrica (Bolivia: 50 Hz); se quita ella y su armónico. 0 = sin filtro
#define MUSCULO_EN_EVALUACION 1   // 1 = después de los 30 s del dedo, la OLED guía la prueba del músculo (35 s)
// 1 = los valores de músculo que se PUBLICAN son fingidos (suben al apretar en la prueba guiada) y van con
// "musculo_simulado": true; los reales siguen en el monitor serie. Hasta que la señal real sirva (con la laptop
// enchufada al cargador, el zumbido de 50 Hz la tapa).
#define MUSCULO_FINGIDO 1
// 1 = solo la prueba guiada del AD8232 en la OLED (sin Wi-Fi, MQTT ni pulso). También al compilar: -DPRUEBA_MUSCULO=1
#ifndef PRUEBA_MUSCULO
#define PRUEBA_MUSCULO 0
#endif

// ---------------------------------------------------------------- hora (si hay internet para NTP)
#define ZONA_HORARIA_S (-4 * 3600)  // Bolivia (UTC-4); sin internet los mensajes salen sin "ts"
