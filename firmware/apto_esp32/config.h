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
#define PIN_LED_ROJO 27        // semáforo de 3 LED (cada uno con su resistencia de 220 Ω): rojo D27, amarillo D25, verde D26.
#define PIN_LED_AMARILLO 25    // Resultado: el LED de su color fijo. Amarillo parpadeando = midiendo / evaluando / sin broker;
#define PIN_LED_VERDE 26       // rojo parpadeando = repite.
#define LED_ANODO_COMUN 0      // 0 = cada LED con el cátodo (pata corta) a GND, HIGH enciende; 1 = ánodo a 3V3, LOW enciende
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
#define MUSCULO_ENVOLVENTE 0.04f  // suavizado de |señal| (~50 ms a 500/s): la «fuerza» de la contracción (antes 0,02)
// Sensibilidad (15/11): con el electrodo LA tocando a medias, LO+ parpadeaba, cada parpadeo de 50 ms rehacía los
// filtros y tiraba 1 s, y casi todos los segundos salían sin valor. Ahora un parpadeo tiene que durar 250 ms para
// contar como despegado y después se esperan 300 ms.
#define MUSCULO_ASENTAR_MS 300    // al pegar los electrodos, 0,3 s sin contar: la salida del AD8232 se acomoda (antes 1 s)
#define MUSCULO_DESPEGADO_MS 250  // LO+ o LO- en alto al menos 250 ms seguidos = despegado (antes 50 ms)
#define MUSCULO_PASA_ALTOS_HZ 5   // desde aquí se mide (antes 10): más sensible a la contracción y al movimiento del brazo
#define MUSCULO_PLANO_MV 15      // si en 1 s la salida varía menos que esto, no hay señal (AD8232 sin alimentación)
#define MUSCULO_TOPE_MV 3050    // salida >= esto o <= 100 mV: el AD8232 está en el tope (saturado), no hay señal útil
#define MUSCULO_RED_HZ 50         // frecuencia de la red eléctrica (Bolivia: 50 Hz); se quita ella y su armónico. 0 = sin filtro
#define MUSCULO_EN_EVALUACION 1   // 1 = después de los 30 s del dedo, la OLED guía la prueba del músculo (35 s)
// Valores de músculo que se publican:
//   0 = siempre los reales (sin electrodos van en null)
//   1 = los reales si hay electrodos puestos; sin electrodos, fingidos (suben al apretar) con "musculo_simulado": true
//   2 = siempre fingidos (los reales van aparte en musculo_real_rms_mv / musculo_real_pico_mv durante la prueba)
#define MUSCULO_FINGIDO 1
// 1 = solo la prueba guiada del AD8232 en la OLED (sin Wi-Fi, MQTT ni pulso). También al compilar: -DPRUEBA_MUSCULO=1
#ifndef PRUEBA_MUSCULO
#define PRUEBA_MUSCULO 0
#endif

// ---------------------------------------------------------------- hora (si hay internet para NTP)
#define ZONA_HORARIA_S (-4 * 3600)  // Bolivia (UTC-4); sin internet los mensajes salen sin "ts"
