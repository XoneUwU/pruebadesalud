// «¿Está apto hoy?» — ESP32: pulso, HRV (RMSSD), SpO2 y movimiento; semáforo en un LED RGB, OLED y zumbador.
//
//   publica  apto/{persona}/esp32           cada 1 s: persona, sesion, pulso_lpm, hrv_rmssd_ms, spo2, dedo,
//                                           movimiento, calidad, electrodos, musculo_rms_mv, musculo_pico_mv
//                                           (y "simulado": true con MODO_SIMULADO)
//   publica  apto/control/modulos/esp32     {"activo": true} con retain al conectar; Last Will {"activo": false}
//   escucha  apto/control/sesion            persona activa (la estación la publica con retain)
//   escucha  apto/{persona}/semaforo        color del semáforo -> LED, OLED y 3 pitidos si es rojo
//
// Pines y opciones en config.h; Wi-Fi y broker en secrets.h (copiar secrets.ejemplo.h). Ver firmware/README.md.
// Es un prototipo de apoyo a la decisión, no un dispositivo médico.

#include <Arduino.h>
#include <WiFi.h>
#include <Wire.h>
#include <math.h>
#include <time.h>

#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>

#include "config.h"
#include "latidos.h"
#include "musculo.h"

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Falta secrets.h: copien secrets.ejemplo.h como secrets.h (misma carpeta) y pongan el Wi-Fi y la IP del broker."
#endif

// WIFI_SSID vacío en secrets.h = modo local: no intenta Wi-Fi ni MQTT.
const bool SIN_RED = sizeof(WIFI_SSID) <= 1;

#if !MODO_SIMULADO
#include "MAX30105.h"       // SparkFun MAX3010x (sirve para el MAX30102)
#include "spo2_algorithm.h"  // maxim_heart_rate_and_oxygen_saturation (FreqS = 25, BUFFER_SIZE = 100)
#endif

// ================================================================ estado general
WiFiClient red;
PubSubClient mqtt(red);
Adafruit_SSD1306 pantalla(128, 64, &Wire, -1);
bool hayPantalla = false;
bool hayMpu = false;
bool haySensor = false;

const char *TEMA_SESION = "apto/control/sesion";
const char *TEMA_CANCELAR = "apto/control/cancelar";  // {"sesion", "motivo"}, retenido: la estación cortó la evaluación
const char *TEMA_MODULO = "apto/control/modulos/esp32";
const char *PRESENCIA_OFF = "{\"modulo\":\"esp32\",\"activo\":false}";

String persona = PERSONA_INICIAL;
String sesion = "";
String colorSemaforo = "";  // "verde", "amarillo", "rojo" o "" (sin dato)
String temaDatos;
String temaSemaforo;

// Lecturas que se publican (NAN = null en el JSON)
bool dedo = false;
float pulsoLpm = NAN;
float hrvMs = NAN;
float spo2 = NAN;
float movimiento = NAN;
float calidad = 0;
float musculoRmsMv = NAN, musculoPicoMv = NAN;  // AD8232 (activación muscular, prototipo): último segundo
bool electrodosOk = false;
float musculoRealRmsMv = NAN, musculoRealPicoMv = NAN;  // los medidos de verdad (con MUSCULO_FINGIDO se publican otros)
const bool FINGIR_MUSCULO = MODO_SIMULADO || (MUSCULO_FINGIDO && !PRUEBA_MUSCULO);
bool musculoApretando = false;      // la prueba guiada está en APRIETA (desde 0,5 s después de la orden)
bool musculoConElectrodos = false;  // en la prueba guiada ya se vieron los electrodos puestos
int faseMusculoAntes = -2;

uint32_t ultimoIntentoWifi = 0;
uint32_t ultimoIntentoMqtt = 0;
uint32_t ultimaPublicacion = 0;
uint32_t ultimaPantalla = 0;
uint32_t ultimoResumen = 0;
bool horaPedida = false;

// Medición guiada (modo local): espera el dedo, cuenta 3-2-1, mide MEDICION_S y muestra el resultado
enum EstadoMedicion { ESPERA, CUENTA, MIDIENDO, RESULTADO, REPOSO, ANUNCIO, NOMBRE, ANALIZANDO, CANCELADA, MUSCULO };
EstadoMedicion estado = SIN_RED ? ESPERA : REPOSO;  // con red, la secuencia empieza cuando la estación abre una evaluación
const uint32_t ANUNCIO_MS = 2500;                    // cuánto se ve «INICIAR ANALISIS» y después el nombre
bool medicionHecha = false;                          // con red: ya se midieron los 30 s de la sesión en curso
String sesionCancelada = "";                         // última sesión que la estación canceló
String motivoCancelada = "";
uint32_t inicioSesionMs = 0, sinBrokerDesde = 0;
const uint32_t SIN_BROKER_MAX_MS = 20000;            // evaluación en curso y 20 s sin broker: se cancela
const uint32_t SIN_RESULTADO_MAX_MS = 15UL * 60000;  // 15 min sin resultado final: se cancela
uint32_t inicioEstado = 0;
String avisoEspera = "";             // p. ej. «Dedo retirado: repite»
const int MAX_LECTURAS = MEDICION_S + 5;
float lecturasPulso[MAX_LECTURAS], lecturasSpo2[MAX_LECTURAS];
int nLecturasPulso = 0, nLecturasSpo2 = 0;
float resPulso = NAN, resHrv = NAN, resSpo2 = NAN;
String resMotivo = "";
bool resAvisoSpo2 = false;

// ================================================================ utilidades
// LED RGB. Para no forzarlo, nunca se encienden los tres canales a la vez (como mucho dos: el amarillo).
void escribirLed(bool r, bool g, bool b) {
  if (r && g && b) b = false;
  bool encendido = LED_ANODO_COMUN ? LOW : HIGH;
  digitalWrite(PIN_LED_R, r ? encendido : !encendido);
  digitalWrite(PIN_LED_G, g ? encendido : !encendido);
  digitalWrite(PIN_LED_B, b ? encendido : !encendido);
}

void mostrarColorEnLed() {
  bool parpadeo = (millis() / 400) % 2;
  if (colorSemaforo == "verde") escribirLed(false, true, false);
  else if (colorSemaforo == "amarillo") escribirLed(true, true, false);
  else if (colorSemaforo == "rojo") escribirLed(true, false, false);
  else if (colorSemaforo == "medir" || colorSemaforo == "evaluando") escribirLed(false, false, true);  // azul: midiendo
  else if (colorSemaforo == "repetir") escribirLed(false, false, parpadeo);        // azul parpadeando: repite
  else if (!SIN_RED && !mqtt.connected()) escribirLed(false, false, true);  // azul: sin conexión al broker
  else escribirLed(false, false, false);
}

bool personaValida(const char *p) {
  size_t n = strlen(p);
  if (n == 0 || n > 24 || strcmp(p, "control") == 0) return false;
  for (size_t i = 0; i < n; i++) {
    char c = p[i];
    if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
  }
  return true;
}

String nombreBonito(const String &p) {
  String n = p;
  if (n.length()) n.setCharAt(0, toupper(n[0]));
  return n;
}

bool horaIso(char *salida, size_t largo) {
  struct tm t;
  if (!getLocalTime(&t, 0) || t.tm_year < 120) return false;  // sin NTP (sin internet): sin hora
  strftime(salida, largo, "%Y-%m-%dT%H:%M:%S", &t);
  return true;
}

void ponerNumero(JsonDocument &doc, const char *clave, float valor, int decimales) {
  if (isnan(valor)) {
    doc[clave] = nullptr;
    return;
  }
  float f = powf(10, decimales);
  doc[clave] = roundf(valor * f) / f;
}

// ================================================================ zumbador (3 pitidos sin bloquear)
int pitidosPendientes = 0;
bool zumbando = false;
uint32_t proximoCambioZumbador = 0;
uint16_t duracionPitido = 150;

// Con tono (TONO_ZUMBADOR_HZ > 0) suena un zumbador pasivo y también uno activo; con 0, HIGH fijo (solo activo).
void zumbador(bool encendido) {
  if (TONO_ZUMBADOR_HZ > 0) {
    if (encendido) tone(PIN_ZUMBADOR, TONO_ZUMBADOR_HZ);
    else noTone(PIN_ZUMBADOR);
  }
  if (!encendido || TONO_ZUMBADOR_HZ == 0) digitalWrite(PIN_ZUMBADOR, encendido ? HIGH : LOW);
}

void pitar(int veces, uint16_t ms = 150) {
  pitidosPendientes = veces;
  duracionPitido = ms;
  zumbando = false;
  zumbador(false);
  proximoCambioZumbador = millis();
}

void cuidarZumbador() {
  if (pitidosPendientes == 0 || millis() < proximoCambioZumbador) return;
  zumbando = !zumbando;
  zumbador(zumbando);
  if (!zumbando) pitidosPendientes--;
  proximoCambioZumbador = millis() + (zumbando ? duracionPitido : 150);
}

// ================================================================ semáforo y persona
void ponerSemaforo(const String &color) {
  if (color == "rojo" && colorSemaforo != "rojo") pitar(3);  // solo al pasar a rojo, no en cada reconexión
  colorSemaforo = color;
  mostrarColorEnLed();
  resMotivo = "Resultado final";
  resAvisoSpo2 = false;
  cambiarEstado(RESULTADO);  // la OLED muestra el resultado hasta la próxima evaluación
  Serial.printf("[esp32] Semaforo de %s: %s\n", persona.c_str(), color.c_str());
}

void armarTemas() {
  temaDatos = "apto/" + persona + "/esp32";
  temaSemaforo = "apto/" + persona + "/semaforo";
}

void cambiarPersona(const char *nueva) {
  if (mqtt.connected()) mqtt.unsubscribe(temaSemaforo.c_str());
  persona = nueva;
  armarTemas();
  colorSemaforo = "";  // hasta que llegue el semáforo (con retain) de la nueva persona
  mostrarColorEnLed();
  if (mqtt.connected()) mqtt.subscribe(temaSemaforo.c_str(), 1);
  Serial.printf("[esp32] Persona activa: %s\n", persona.c_str());
}

// ¿Hay una evaluación en curso en la placa? (con red: desde el anuncio hasta que llega el resultado)
bool enEvaluacion() {
  return !SIN_RED && estado != REPOSO && estado != RESULTADO && estado != CANCELADA;
}

// Corta la evaluación: la OLED dice CANCELADA y el motivo, el LED se apaga y después vuelve a «Listo».
void cancelarEvaluacion(const char *motivo) {
  motivoCancelada = motivo;
  medicionHecha = false;
  colorSemaforo = "";
  mostrarColorEnLed();
  pitar(2, 300);
  cambiarEstado(CANCELADA);
  Serial.printf("[esp32] Evaluacion CANCELADA: %s\n", motivo);
}

void alMensaje(char *tema, byte *carga, unsigned int largo) {
  String t(tema);  // copia: el buffer de PubSubClient se reutiliza
  JsonDocument doc;
  if (deserializeJson(doc, carga, largo)) return;
  if (t == TEMA_SESION) {
    const char *p = doc["persona"] | "";
    if (personaValida(p) && persona != p) cambiarPersona(p);
    String nueva = String((const char *)(doc["sesion"] | ""));
    if (nueva != sesion && nueva == sesionCancelada) {  // (al reconectar) esa sesión ya se había cancelado
      sesion = nueva;
    } else if (nueva != sesion) {  // empezó otra evaluación: el color anterior ya no vale
      sesion = nueva;
      inicioSesionMs = millis();
      sinBrokerDesde = 0;
      colorSemaforo = "evaluando";  // azul hasta que el coordinador publique el resultado de ESTA sesión
      mostrarColorEnLed();
      Serial.printf("[esp32] Evaluacion en curso (sesion %s): LED azul hasta el resultado\n", sesion.c_str());
      avisoEspera = "";
      medicionHecha = false;
      cambiarEstado(ANUNCIO);  // OLED: INICIAR ANALISIS -> nombre -> dedo -> 3-2-1 -> 30 s -> analizando -> resultado
      pitar(1, 200);
    }
  } else if (t == temaSemaforo) {
    // El color solo se muestra si es el resultado final de la sesión en curso (todas las pruebas, no solo el sensor).
    // Un semáforo retenido de una evaluación anterior se ignora. Sin "sesion" en el mensaje (simulador), se acepta.
    String deSesion = String((const char *)(doc["sesion"] | ""));
    if (deSesion.length() && sesion.length() && deSesion != sesion) return;
    String color = doc["color"] | "";
    if (color == "verde" || color == "amarillo" || color == "rojo") ponerSemaforo(color);
  } else if (t == TEMA_CANCELAR) {  // la estación cortó la evaluación
    sesionCancelada = String((const char *)(doc["sesion"] | ""));
    if (sesionCancelada.length() && sesionCancelada == sesion && enEvaluacion())
      cancelarEvaluacion(doc["motivo"] | "Cancelada en la estacion");
  }
}

// ================================================================ Wi-Fi y MQTT (sin bloquear)
void cuidarWifi() {
  if (SIN_RED) return;
  if (WiFi.status() == WL_CONNECTED) {
    if (!horaPedida) {  // NTP: si hay internet, los mensajes llevan "ts"
      configTime(ZONA_HORARIA_S, 0, "pool.ntp.org", "time.google.com");
      horaPedida = true;
      Serial.printf("[esp32] Wi-Fi conectado: %s\n", WiFi.localIP().toString().c_str());
    }
    return;
  }
  if (ultimoIntentoWifi != 0 && millis() - ultimoIntentoWifi < CADA_WIFI_MS) return;
  ultimoIntentoWifi = millis();
  Serial.printf("[esp32] Conectando a Wi-Fi %s...\n", WIFI_SSID);
  WiFi.disconnect();
  WiFi.begin(WIFI_SSID, WIFI_PASS);  // no espera: el estado se revisa en la próxima vuelta
}

void publicarPresencia() {
  JsonDocument doc;
  doc["modulo"] = "esp32";
  doc["activo"] = true;
  char ts[25];
  if (horaIso(ts, sizeof(ts))) doc["ts"] = ts;
  char buf[128];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(TEMA_MODULO, (const uint8_t *)buf, n, true);
}

void cuidarMqtt() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connected()) {
    mqtt.loop();
    return;
  }
  if (ultimoIntentoMqtt != 0 && millis() - ultimoIntentoMqtt < CADA_MQTT_MS) return;
  ultimoIntentoMqtt = millis();
  String id = "esp32-" + String((uint32_t)ESP.getEfuseMac(), HEX);
  bool ok = strlen(MQTT_USER) > 0
                ? mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASS, TEMA_MODULO, 1, true, PRESENCIA_OFF)
                : mqtt.connect(id.c_str(), nullptr, nullptr, TEMA_MODULO, 1, true, PRESENCIA_OFF);
  if (!ok) {
    Serial.printf("[esp32] MQTT %s:%d no respondio (estado %d); reintento en %d s\n", MQTT_HOST, MQTT_PORT,
                  mqtt.state(), CADA_MQTT_MS / 1000);
    mostrarColorEnLed();
    return;
  }
  Serial.println("[esp32] Conectado a MQTT");
  publicarPresencia();
  mqtt.subscribe(TEMA_SESION, 1);          // retenido: llega enseguida la última sesión
  mqtt.subscribe(TEMA_CANCELAR, 1);        // retenido: si esa sesión se canceló, no se anuncia
  mqtt.subscribe(temaSemaforo.c_str(), 1);  // retenido: llega el color actual
  mostrarColorEnLed();
}

// ================================================================ MAX30102: pulso, HRV y SpO2
#if !MODO_SIMULADO
MAX30105 sensor;
const uint32_t PERIODO_MUESTRA_MS = 10;  // 400 muestras/s con promedio de 4 = 100 por segundo
uint32_t muestras = 0;                   // reloj del sensor: hora de cada muestra = muestras * 10 ms

// Intervalos entre latidos aceptados (anillo) y latidos detectados (para la calidad). Tipos en latidos.h.
const int MAX_INTERVALOS = 96;
Intervalo intervalos[MAX_INTERVALOS];
int nIntervalos = 0, siguienteIntervalo = 0;
const int MAX_EVENTOS = 48;
Evento eventos[MAX_EVENTOS];
int nEventos = 0, siguienteEvento = 0;

uint32_t ultimoLatido = 0;
bool ultimoAceptado = false;
int rechazosSeguidos = 0;

uint32_t bufIr[BUFFER_SIZE], bufRojo[BUFFER_SIZE];  // SpO2: 100 muestras a 25 Hz = 4 s
int nBuf = 0, diezmo = 0;

uint32_t ahoraSensor() { return muestras * PERIODO_MUESTRA_MS; }

// Detector de latidos propio. checkForBeat de SparkFun descarta los latidos con más de 1000 cuentas de pico a pico,
// y con este sensor y BRILLO_LED_SENSOR 60 la señal tiene 3000 a 13000: perdía casi todos los latidos.
// IR filtrado - línea base, invertido (el IR baja con cada latido); un latido = máximo local sobre el 40 % de la
// envolvente, quedándose con el mayor dentro de 300 ms. Después de cada latido hay un período refractario
// (60 % del intervalo típico, entre 300 y 400 ms) para no contar la onda dicrótica como otro latido.
// Probado con capturas reales (DEPURAR_IR).
float irFiltrado = 0, irBase = 0, envolvente = 0, acAnterior = 0, acAnterior2 = 0;
uint32_t muestrasDetector = 0;
bool hayCandidato = false;
uint32_t tCandidato = 0;
float vCandidato = 0;
uint32_t tConfirmado = 0;
float intervaloTipico = 700;

void reiniciarDetector() {
  muestrasDetector = 0;
  envolvente = acAnterior = acAnterior2 = 0;
  hayCandidato = false;
  tConfirmado = 0;
  intervaloTipico = 700;
}

void alLatir(uint32_t t);

void confirmarLatido(uint32_t t) {
  if (tConfirmado) {
    uint32_t d = t - tConfirmado;
    if (d >= 300 && d <= 2000) intervaloTipico += 0.25f * ((float)d - intervaloTipico);
  }
  tConfirmado = t;
  alLatir(t);
}

void detectarLatido(uint32_t ir) {
  if (muestrasDetector++ == 0) irFiltrado = irBase = ir;
  irFiltrado += 0.25f * ((float)ir - irFiltrado);  // pasa bajos (~40 ms)
  irBase += 0.02f * ((float)ir - irBase);          // línea de base (~0,5 s)
  float ac = irBase - irFiltrado;
  envolvente = max(fabsf(ac), envolvente * 0.98f);
  uint32_t t = ahoraSensor() - PERIODO_MUESTRA_MS;  // el máximo está en la muestra anterior
  float refractario = constrain(0.6f * intervaloTipico, 300.0f, 400.0f);
  bool fueraRefractario = tConfirmado == 0 || (float)(t - tConfirmado) >= refractario;
  if (muestrasDetector > 100 && fueraRefractario && acAnterior > acAnterior2 && acAnterior >= ac &&
      acAnterior > 0.4f * envolvente) {
    if (hayCandidato && t - tCandidato < 300) {
      if (acAnterior > vCandidato) tCandidato = t, vCandidato = acAnterior;
    } else {
      if (hayCandidato) confirmarLatido(tCandidato);
      hayCandidato = true, tCandidato = t, vCandidato = acAnterior;
    }
  }
  if (hayCandidato && ahoraSensor() - tCandidato > 300) {
    confirmarLatido(tCandidato);
    hayCandidato = false;
  }
  acAnterior2 = acAnterior;
  acAnterior = ac;
}

const Intervalo &intervaloReciente(int k) {  // k = 0 es el más nuevo
  return intervalos[(siguienteIntervalo - 1 - k + MAX_INTERVALOS) % MAX_INTERVALOS];
}

float promedioIntervalos(int cuantos) {
  int n = min(cuantos, nIntervalos);
  if (n == 0) return NAN;
  float suma = 0;
  for (int k = 0; k < n; k++) suma += intervaloReciente(k).ms;
  return suma / n;
}

void reiniciarLatidos() {
  nIntervalos = siguienteIntervalo = 0;
  nEventos = siguienteEvento = 0;
  ultimoLatido = 0;
  ultimoAceptado = false;
  rechazosSeguidos = 0;
  nBuf = diezmo = 0;
  reiniciarDetector();
  pulsoLpm = hrvMs = spo2 = NAN;
}

void alLatir(uint32_t t) {
  if (ultimoLatido == 0) {
    ultimoLatido = t;
    return;
  }
  uint32_t ibi = t - ultimoLatido;
  ultimoLatido = t;
  bool ok = ibi >= 300 && ibi <= 2000;  // 30 a 200 lpm
  float ref = promedioIntervalos(4);
  if (ok && !isnan(ref) && fabsf((float)ibi - ref) > 0.30f * ref) ok = false;  // salto brusco: ruido
  eventos[siguienteEvento] = {t, ok};
  siguienteEvento = (siguienteEvento + 1) % MAX_EVENTOS;
  if (nEventos < MAX_EVENTOS) nEventos++;
  if (ok) {
    intervalos[siguienteIntervalo] = {t, (uint16_t)ibi, ultimoAceptado};
    siguienteIntervalo = (siguienteIntervalo + 1) % MAX_INTERVALOS;
    if (nIntervalos < MAX_INTERVALOS) nIntervalos++;
    rechazosSeguidos = 0;
  } else if (++rechazosSeguidos > 4) {  // la referencia quedó mal: se empieza de nuevo
    nIntervalos = siguienteIntervalo = 0;
    rechazosSeguidos = 0;
  }
  ultimoAceptado = ok;
}

void calcularSpo2() {
  int32_t valor, pulsoMaxim;
  int8_t valorOk, pulsoOk;
  maxim_heart_rate_and_oxygen_saturation(bufIr, BUFFER_SIZE, bufRojo, &valor, &valorOk, &pulsoMaxim, &pulsoOk);
  spo2 = (valorOk && valor >= 70 && valor <= 100) ? (float)valor : NAN;
}

void leerSensor() {
  sensor.check();
  while (sensor.available()) {
    uint32_t ir = sensor.getFIFOIR();
    uint32_t rojo = sensor.getFIFORed();
    sensor.nextSample();
    muestras++;
    bool hayDedo = ir > UMBRAL_DEDO;
    if (hayDedo != dedo) {
      dedo = hayDedo;
      reiniciarLatidos();
      Serial.println(dedo ? "[esp32] Dedo detectado" : "[esp32] Sin dedo");
    }
#ifdef DEPURAR_IR
    Serial.printf("R %lu %lu %d\n", (unsigned long)ir, (unsigned long)rojo, (int)dedo);
#endif
    if (!dedo) continue;
    detectarLatido(ir);
    if (++diezmo >= 4) {  // 100 -> 25 muestras por segundo para spo2_algorithm
      diezmo = 0;
      bufIr[nBuf] = ir;
      bufRojo[nBuf] = rojo;
      if (++nBuf >= BUFFER_SIZE) {  // cada ~4 s
        calcularSpo2();
        nBuf = 0;
      }
    }
  }
}

// Pulso, RMSSD y calidad a partir de los intervalos (se llama una vez por segundo)
void calcularLecturas() {
  uint32_t ahora = ahoraSensor();
  if (!dedo) {
    pulsoLpm = hrvMs = spo2 = NAN;
    calidad = 0;
    return;
  }
  bool reciente = nIntervalos > 0 && ahora - intervaloReciente(0).t < 5000;
  pulsoLpm = reciente ? 60000.0f / promedioIntervalos(4) : NAN;
  // RMSSD de los últimos 30 s: diferencias entre intervalos seguidos
  float suma = 0;
  int n = 0;
  for (int k = 0; k + 1 < nIntervalos; k++) {
    const Intervalo &nuevo = intervaloReciente(k);
    if (ahora - nuevo.t > VENTANA_HRV_MS) break;
    if (!nuevo.contiguo) continue;
    float d = (float)nuevo.ms - (float)intervaloReciente(k + 1).ms;
    suma += d * d;
    n++;
  }
  hrvMs = n >= 5 ? sqrtf(suma / n) : NAN;
  // Calidad: latidos aceptados / detectados en los últimos 10 s; a la mitad si hay movimiento
  int aceptados = 0, total = 0;
  for (int k = 0; k < nEventos; k++) {
    const Evento &e = eventos[(siguienteEvento - 1 - k + MAX_EVENTOS) % MAX_EVENTOS];
    if (ahora - e.t > 10000) break;
    total++;
    aceptados += e.aceptado;
  }
  calidad = total ? (float)aceptados / total : 0;
  if (!reciente) calidad = 0;
  if (!isnan(movimiento) && movimiento > UMBRAL_MOVIMIENTO) calidad *= 0.5f;
}

// ================================================================ MPU6050 (lectura directa por I2C)
uint32_t ultimoMpu = 0, inicioVentanaMpu = 0;
double sumaA = 0, sumaA2 = 0;
int nA = 0;

bool iniciarMpu() {
  Wire.beginTransmission(DIR_MPU6050);
  Wire.write(0x6B);  // PWR_MGMT_1: despertar
  Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  Wire.beginTransmission(DIR_MPU6050);
  Wire.write(0x1C);  // ACCEL_CONFIG: ±2 g (16384 cuentas por g)
  Wire.write(0x00);
  return Wire.endTransmission() == 0;
}

bool leerAceleracion(float &modulo) {
  Wire.beginTransmission(DIR_MPU6050);
  Wire.write(0x3B);  // ACCEL_XOUT_H
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom((uint16_t)DIR_MPU6050, (size_t)6, true) != 6) return false;
  int16_t ax = (Wire.read() << 8) | Wire.read();
  int16_t ay = (Wire.read() << 8) | Wire.read();
  int16_t az = (Wire.read() << 8) | Wire.read();
  modulo = sqrtf((float)ax * ax + (float)ay * ay + (float)az * az) / 16384.0f;
  return true;
}

void cuidarMpu() {
  if (!hayMpu || millis() - ultimoMpu < CADA_MPU_MS) return;
  ultimoMpu = millis();
  float a;
  if (leerAceleracion(a)) {
    sumaA += a;
    sumaA2 += (double)a * a;
    nA++;
  }
  if (millis() - inicioVentanaMpu >= 1000) {  // movimiento = desviación de |aceleración| en 1 s
    if (nA > 5) {
      double media = sumaA / nA;
      movimiento = sqrt(fmax(0.0, sumaA2 / nA - media * media));
    }
    sumaA = sumaA2 = 0;
    nA = 0;
    inicioVentanaMpu = millis();
  }
}
#endif  // !MODO_SIMULADO

// ================================================================ modo simulado (sin sensores)
#if MODO_SIMULADO
void calcularLecturas() {
  float t = millis() / 1000.0f;
  dedo = true;
#ifdef PULSO_FORZADO  // para probar los colores sin sensor: -DMODO_SIMULADO=1 -DPULSO_FORZADO=130
  pulsoLpm = PULSO_FORZADO;
#else
  pulsoLpm = 72 + 4 * sinf(t / 20) + random(-10, 11) / 10.0f;
#endif
  hrvMs = 45 + 5 * sinf(t / 33) + random(-20, 21) / 10.0f;
  spo2 = 97 + random(0, 3);
  movimiento = 0.01f + random(0, 20) / 1000.0f;
  calidad = 0.95f;
}
#endif

// ================================================================ publicación y pantalla
void publicarDatos() {
  JsonDocument doc;
  doc["persona"] = persona;
  if (sesion.length()) doc["sesion"] = sesion;
  // Con red, las lecturas solo valen durante los MEDICION_S de la medición guiada: fuera de ella van en null
  // (aunque el dedo siga puesto), así el coordinador y la estación solo usan lo medido en esos 30 s.
  bool vale = dedo && (SIN_RED || estado == MIDIENDO);
  ponerNumero(doc, "pulso_lpm", vale ? pulsoLpm : NAN, 1);
  ponerNumero(doc, "hrv_rmssd_ms", vale ? hrvMs : NAN, 1);
  ponerNumero(doc, "spo2", vale ? spo2 : NAN, 0);
  doc["dedo"] = dedo;
  if (!SIN_RED) {  // en qué paso de la medición guiada está la placa (la estación lo muestra y habilita «Continuar»)
    const char *fases[] = {"espera", "cuenta", "midiendo", "resultado", "reposo", "anuncio", "nombre", "listo", "cancelada", "musculo"};
    doc["fase"] = fases[estado];
    if (estado == MIDIENDO) doc["quedan_s"] = max(0, MEDICION_S - (int)((millis() - inicioEstado) / 1000));
    if (estado == MUSCULO) {
      int total = 0;
      for (int i = 0; i < N_FASES_MUSCULO; i++) total += FASES_MUSCULO[i].s;
      doc["quedan_s"] = max(0, total - (int)((millis() - inicioEstado) / 1000));
      // La orden en curso: la estación la muestra y el coordinador separa lo medido en APRIETA y en DESCANSA
      int quedanOrden;
      uint32_t enFase;
      int f = faseMusculo(millis() - inicioEstado, quedanOrden, enFase);
      if (f >= 0) {
        String orden = FASES_MUSCULO[f].nombre;
        orden.toLowerCase();  // "preparate", "aprieta", "espera" o "descansa"
        doc["musculo_orden"] = orden;
      }
    }
    if (medicionHecha) {  // resumen de los 30 s: queda disponible aunque se retire el dedo
      doc["medicion_lista"] = true;
      ponerNumero(doc, "pulso_medido_lpm", resPulso, 1);
      ponerNumero(doc, "hrv_medido_ms", resHrv, 1);
      ponerNumero(doc, "spo2_medido", resSpo2, 0);
    }
  }
  ponerNumero(doc, "movimiento", movimiento, 3);
  ponerNumero(doc, "calidad", calidad, 2);
  // Activación muscular (prototipo con AD8232): mV a la salida del AD8232, del último segundo
  doc["electrodos"] = electrodosOk;
  ponerNumero(doc, "musculo_rms_mv", musculoRmsMv, 1);
  ponerNumero(doc, "musculo_pico_mv", musculoPicoMv, 1);
  if (FINGIR_MUSCULO) doc["musculo_simulado"] = true;  // los dos valores de músculo son fingidos
  if (MODO_SIMULADO) doc["simulado"] = true;
  char ts[25];
  if (horaIso(ts, sizeof(ts))) doc["ts"] = ts;
  doc["fuente"] = "esp32";
  char buf[512];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(temaDatos.c_str(), (const uint8_t *)buf, n, false);
}

// ================================================================ medición guiada (modo local, sin red)
float mediana(float *v, int n) {
  float c[MAX_LECTURAS];
  for (int i = 0; i < n; i++) c[i] = v[i];
  for (int i = 1; i < n; i++)  // inserción: n es chico
    for (int j = i; j > 0 && c[j] < c[j - 1]; j--) std::swap(c[j], c[j - 1]);
  return n % 2 ? c[n / 2] : (c[n / 2 - 1] + c[n / 2]) / 2;
}

void cambiarEstado(EstadoMedicion nuevo) {
  estado = nuevo;
  inicioEstado = millis();
  const char *nombres[] = {"ESPERA", "CUENTA", "MIDIENDO", "RESULTADO", "REPOSO", "ANUNCIO", "NOMBRE", "ANALIZANDO", "CANCELADA", "MUSCULO"};
  Serial.printf("[esp32] Estado: %s\n", nombres[nuevo]);
}

// Reglas del coordinador sin línea base para el pulso del sensor (100 = 1 punto, 120 = 2), más el aviso de pulso
// bajo. El SpO2 bajo solo agrega un aviso, no cambia el color (regla del proyecto). La HRV no se juzga sin base.
void terminarMedicion() {
  resPulso = nLecturasPulso ? mediana(lecturasPulso, nLecturasPulso) : NAN;
  resSpo2 = nLecturasSpo2 ? mediana(lecturasSpo2, nLecturasSpo2) : NAN;
  // resHrv se guarda al terminar los 30 s del dedo (después viene la prueba del músculo y el dedo ya no está)
  resAvisoSpo2 = !isnan(resSpo2) && resSpo2 < 92;
  String color;
  if (nLecturasPulso < MEDICION_S / 3 || isnan(resPulso)) {
    color = "repetir";
    resMotivo = "Senal debil: repite";
    pitar(2, 500);
  } else if (resPulso >= 120) {
    color = "rojo";
    resMotivo = "Pulso en reposo alto";
    pitar(3);
  } else if (resPulso >= 100) {
    color = "amarillo";
    resMotivo = "Pulso en reposo alto";
    pitar(1, 400);
  } else if (resPulso < 40) {  // posible pero riesgoso: se muestra, no se descarta (lo imposible ya no llega aquí:
    color = "rojo";            // los intervalos fuera de 30 a 200 lpm se rechazan en alLatir)
    resMotivo = "Pulso muy bajo";
    pitar(3);
  } else if (resPulso < 50) {
    color = "amarillo";
    resMotivo = "Pulso bajo";
    pitar(1, 400);
  } else {
    color = "verde";
    resMotivo = "Sin alertas";
    pitar(1, 80);
  }
  colorSemaforo = color;
  mostrarColorEnLed();
  Serial.printf("[esp32] Resultado %s: %s pulso=%.1f (%d lecturas buenas) hrv=%.1f spo2=%.0f aviso_spo2=%d\n",
                persona.c_str(), color.c_str(), resPulso, nLecturasPulso, resHrv, resSpo2, resAvisoSpo2);
  cambiarEstado(RESULTADO);
}

// Se llama una vez por segundo, después de calcularLecturas()
void guardarLectura() {
  if (estado != MIDIENDO) return;
  if (dedo && !isnan(pulsoLpm) && calidad >= 0.5f && nLecturasPulso < MAX_LECTURAS)
    lecturasPulso[nLecturasPulso++] = pulsoLpm;
  if (dedo && !isnan(spo2) && nLecturasSpo2 < MAX_LECTURAS) lecturasSpo2[nLecturasSpo2++] = spo2;
}

bool dedoAntes = false;

void cuidarMedicion() {
  if (enEvaluacion()) {  // problemas que cortan la evaluación: sin broker 20 s, o 15 min sin resultado final
    if (mqtt.connected()) sinBrokerDesde = 0;
    else if (sinBrokerDesde == 0) sinBrokerDesde = millis();
    else if (millis() - sinBrokerDesde >= SIN_BROKER_MAX_MS) {
      sinBrokerDesde = 0;
      cancelarEvaluacion("Sin conexion");
    }
    if (enEvaluacion() && millis() - inicioSesionMs >= SIN_RESULTADO_MAX_MS) cancelarEvaluacion("Sin resultado");
  }
  uint32_t t = millis() - inicioEstado;
  if (estado != MUSCULO) musculoApretando = false;
  bool puso = dedo && !dedoAntes;
  dedoAntes = dedo;
  switch (estado) {
    case ESPERA:
      if (dedo) {
        avisoEspera = "";
        cambiarEstado(CUENTA);
        pitar(1, 60);
      }
      break;
    case CUENTA:
      if (!dedo) {
        avisoEspera = "Dedo retirado: repite";
        cambiarEstado(ESPERA);
      } else if (t >= 3000) {
        nLecturasPulso = nLecturasSpo2 = 0;
        colorSemaforo = "medir";
        mostrarColorEnLed();
        pitar(1, 300);
        cambiarEstado(MIDIENDO);
      }
      break;
    case MIDIENDO:
      if (!dedo) {
        avisoEspera = "Dedo retirado: repite";
        colorSemaforo = SIN_RED ? "" : "evaluando";
        mostrarColorEnLed();
        cambiarEstado(ESPERA);
      } else if (t >= MEDICION_S * 1000UL) {
        resHrv = hrvMs;
        if (SIN_RED && nLecturasPulso < MEDICION_S / 3) {
          terminarMedicion();  // REPITE, sin la prueba del músculo
        } else if (!SIN_RED && nLecturasPulso < MEDICION_S / 3) {  // menos de 10 s de señal buena: se repite
          avisoEspera = "Senal debil: repite";
          colorSemaforo = "evaluando";
          mostrarColorEnLed();
          pitar(2, 500);
          cambiarEstado(ESPERA);
        } else {
          resPulso = nLecturasPulso ? mediana(lecturasPulso, nLecturasPulso) : NAN;
          resSpo2 = nLecturasSpo2 ? mediana(lecturasSpo2, nLecturasSpo2) : NAN;
          empezarMusculo();
        }
      }
      break;
    case MUSCULO: {  // prueba guiada del músculo; si en 4 s no hay electrodos puestos, se omite
      int quedan;
      uint32_t enFase;
      int f = faseMusculo(t, quedan, enFase);
      if (electrodosOk) musculoConElectrodos = true;
      if (f < 0 || (t >= 4000 && !musculoConElectrodos)) {
        if (!musculoConElectrodos) Serial.println("[esp32] Musculo: sin electrodos, se omite");
        terminarMusculo();
        break;
      }
      musculoApretando = FASES_MUSCULO[f].aprieta && enFase >= 500;  // medio segundo para reaccionar
      if (f != faseMusculoAntes) {
        faseMusculoAntes = f;
        if (FASES_MUSCULO[f].aprieta) pitar(2, 120);
        else if (strcmp(FASES_MUSCULO[f].nombre, "DESCANSA") == 0) pitar(1, 300);
        Serial.printf("[esp32] Musculo: %s\n", FASES_MUSCULO[f].nombre);
      }
      break;
    }
    case ANUNCIO:  // «INICIAR ANALISIS» y después el nombre de quien se evalúa
      if (t >= ANUNCIO_MS) cambiarEstado(NOMBRE);
      break;
    case NOMBRE:
      if (t >= ANUNCIO_MS) {
        avisoEspera = "";
        cambiarEstado(ESPERA);
      }
      break;
    case ANALIZANDO:  // el sensor ya midió; el color llega con el semáforo de la sesión
    case REPOSO:
      break;
    case CANCELADA:
      if (t >= 6000) cambiarEstado(REPOSO);
      break;
    case RESULTADO:
      if (!SIN_RED) break;  // con red el resultado queda hasta la próxima evaluación
      if (puso) {  // retiró el dedo y lo volvió a poner: nueva medición
        colorSemaforo = "";
        mostrarColorEnLed();
        avisoEspera = "";
        cambiarEstado(CUENTA);
        pitar(1, 60);
      }
      break;
  }
}

// Después de los 30 s del dedo: la prueba del músculo (o directo al final si está desactivada)
void empezarMusculo() {
  if (!MUSCULO_EN_EVALUACION) {
    terminarMusculo();
    return;
  }
  musculoConElectrodos = false;
  faseMusculoAntes = -2;
  colorSemaforo = SIN_RED ? "medir" : "evaluando";  // azul
  mostrarColorEnLed();
  cambiarEstado(MUSCULO);
}

// Fin de la prueba del músculo. Sin red: el resultado del pulso. Con red: el resultado lo da el coordinador al
// terminar TODAS las pruebas; aquí la medición queda lista y solo se espera.
void terminarMusculo() {
  musculoApretando = false;
  if (SIN_RED) {
    terminarMedicion();
    return;
  }
  medicionHecha = true;
  colorSemaforo = "evaluando";
  mostrarColorEnLed();
  pitar(1, 300);
  cambiarEstado(ANALIZANDO);
}

// Pitido corto en cada número de la cuenta 3-2-1
int ultimoNumeroCuenta = -1;
void pitarCuenta() {
  if (estado != CUENTA) {
    ultimoNumeroCuenta = -1;
    return;
  }
  int n = 3 - (millis() - inicioEstado) / 1000;
  if (n != ultimoNumeroCuenta && n >= 1 && n < 3) pitar(1, 60);  // el «3» ya pitó al entrar
  ultimoNumeroCuenta = n;
}

void centrar(const String &texto, int tam, int y) {
  pantalla.setTextSize(tam);
  int x = (128 - (int)texto.length() * 6 * tam) / 2;
  pantalla.setCursor(max(0, x), y);
  pantalla.print(texto);
}

void dibujarMedicion() {
  pantalla.clearDisplay();
  pantalla.setTextColor(SSD1306_WHITE);
  pantalla.setTextSize(1);
  pantalla.setCursor(0, 0);
  pantalla.print(nombreBonito(persona));
  uint32_t t = millis() - inicioEstado;
  switch (estado) {
    case ESPERA:
      centrar("Coloca", 2, 16);
      centrar("tu dedo", 2, 34);
      if (avisoEspera.length()) centrar(avisoEspera, 1, 56);
      break;
    case CUENTA:
      centrar("Preparate", 1, 10);
      centrar(String(max(1, 3 - (int)(t / 1000))), 4, 26);
      break;
    case MIDIENDO: {
      int quedan = MEDICION_S - (int)(t / 1000);
      centrar("No te muevas", 1, 10);
      pantalla.setTextSize(4);
      pantalla.setCursor(0, 26);
      pantalla.printf("%2d", max(1, quedan));
      pantalla.setTextSize(1);
      pantalla.setCursor(60, 28);
      if (isnan(pulsoLpm)) pantalla.print("Pulso --");
      else pantalla.printf("Pulso %.0f", pulsoLpm);
      pantalla.setCursor(60, 40);
      if (isnan(spo2)) pantalla.print("SpO2 --");
      else pantalla.printf("SpO2 %.0f%%", spo2);
      // barra de progreso
      pantalla.drawRect(0, 60, 128, 4, SSD1306_WHITE);
      pantalla.fillRect(0, 60, (int)(128 * min(1.0f, t / (MEDICION_S * 1000.0f))), 4, SSD1306_WHITE);
      break;
    }
    case ANUNCIO:
      centrar("INICIAR", 2, 16);
      centrar("ANALISIS", 2, 36);
      break;
    case NOMBRE:
      centrar("Se evalua a", 1, 12);
      centrar(nombreBonito(persona), 3, 28);
      break;
    case ANALIZANDO:
      // Lo medido en los 30 s queda guardado y a la vista mientras siguen las demás pruebas en la estación.
      centrar("MEDIDO", 2, 10);
      pantalla.setTextSize(1);
      pantalla.setCursor(0, 30);
      if (isnan(resPulso)) pantalla.print("Pulso --");
      else pantalla.printf("Pulso %.0f", resPulso);
      pantalla.setCursor(66, 30);
      if (isnan(resSpo2)) pantalla.print("SpO2 --");
      else pantalla.printf("SpO2 %.0f%%", resSpo2);
      pantalla.setCursor(0, 40);
      if (!isnan(resHrv)) pantalla.printf("HRV %.0f ms", resHrv);
      centrar("Retira el dedo y sigue", 1, 50);
      break;
    case MUSCULO: {
      int quedan, nivel;
      uint32_t enFase;
      int f = faseMusculo(t, quedan, enFase);
      dibujarFaseMusculo(f, quedan, avisoMusculo(nivel));
      break;
    }
    case CANCELADA:
      centrar("CANCELADA", 2, 16);
      centrar(motivoCancelada, 1, 40);
      break;
    case REPOSO:
      centrar("Listo", 2, 14);
      centrar("Inicia la evaluacion", 1, 36);
      centrar("en la estacion", 1, 46);
      break;
    case RESULTADO: {
      String c = colorSemaforo == "repetir" ? String("REPITE") : colorSemaforo;
      c.toUpperCase();
      centrar(c, 2, 10);
      pantalla.setTextSize(1);
      pantalla.setCursor(0, 30);
      if (isnan(resPulso)) pantalla.print("Pulso --");
      else pantalla.printf("Pulso %.0f", resPulso);
      pantalla.setCursor(66, 30);
      if (isnan(resSpo2)) pantalla.print("SpO2 --");
      else pantalla.printf("SpO2 %.0f%%", resSpo2);
      pantalla.setCursor(0, 40);
      if (!isnan(resHrv)) pantalla.printf("HRV %.0f ms", resHrv);
      centrar(resMotivo, 1, 48);
      if (resAvisoSpo2) centrar("Oxigeno bajo", 1, 57);  // valor posible pero bajo: se muestra como aviso
      break;
    }
  }
  if (!SIN_RED && (estado == REPOSO || estado == ANALIZANDO || estado == ESPERA) && !mqtt.connected()) {
    pantalla.fillRect(0, 56, 128, 8, SSD1306_BLACK);
    centrar(WiFi.status() == WL_CONNECTED ? "Sin broker MQTT" : "Sin Wi-Fi", 1, 56);
  }
  pantalla.display();
}

void dibujarPantalla() {
  if (!hayPantalla) return;
  dibujarMedicion();  // la misma secuencia guiada con red (la abre la estación) y sin red
}

// ================================================================ arranque y vuelta principal
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.printf("\n[esp32] Esta apto hoy - %s\n", MODO_SIMULADO ? "MODO SIMULADO (sin sensores)" : "sensores");
  pinMode(PIN_LED_R, OUTPUT);
  pinMode(PIN_LED_G, OUTPUT);
  pinMode(PIN_LED_B, OUTPUT);
  pinMode(PIN_ZUMBADOR, OUTPUT);
  digitalWrite(PIN_ZUMBADOR, LOW);
  // Prueba del cableado al arrancar: rojo, verde y azul de a uno (nunca juntos) y un pitido corto
  escribirLed(true, false, false);
  delay(400);
  escribirLed(false, true, false);
  delay(400);
  escribirLed(false, false, true);
  delay(400);
  escribirLed(false, false, false);
  zumbador(true);
  delay(150);
  zumbador(false);
  delay(200);
  escribirLed(false, false, !SIN_RED);  // azul (sin broker) solo si hay red configurada
  if (SIN_RED) Serial.println("[esp32] Modo local: WIFI_SSID vacio, sin Wi-Fi ni MQTT");

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  Serial.print("[esp32] I2C encontrados:");
  for (uint8_t d = 1; d < 127; d++) {
    Wire.beginTransmission(d);
    if (Wire.endTransmission() == 0) Serial.printf(" 0x%02X", d);
  }
  Serial.println();
  uint8_t dirOled = 0;
  for (uint8_t d : {(uint8_t)DIR_OLED, (uint8_t)0x3D}) {  // algunas OLED de 0,96" vienen en 0x3D
    Wire.beginTransmission(d);
    if (Wire.endTransmission() == 0) {
      dirOled = d;
      break;
    }
  }
  hayPantalla = dirOled && pantalla.begin(SSD1306_SWITCHCAPVCC, dirOled);
  Serial.printf("[esp32] OLED: %s (0x%02X)\n", hayPantalla ? "si" : "no encontrada", dirOled);
#if !MODO_SIMULADO
  haySensor = sensor.begin(Wire, I2C_SPEED_FAST);
  if (haySensor) sensor.setup(BRILLO_LED_SENSOR, 4, 2, 400, 411, 4096);  // promedio 4, rojo+IR, 400 -> 100/s
  Serial.printf("[esp32] MAX30102: %s\n", haySensor ? "si" : "NO encontrado (revisen el cableado)");
  hayMpu = iniciarMpu();
  Serial.printf("[esp32] MPU6050: %s\n", hayMpu ? "si" : "no encontrado (movimiento = null)");
#endif

  armarTemas();
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(alMensaje);
  mqtt.setBufferSize(512);
  mqtt.setKeepAlive(15);
  mqtt.setSocketTimeout(MQTT_ESPERA_S);
  iniciarMusculo();  // AD8232: la tarea de 500 lecturas por segundo
}

// ================================================================ AD8232: activación muscular (prototipo)
// Una tarea aparte lee el ADC cada 2 ms: 500 lecturas por segundo de verdad (en loop() la OLED la frenaba ~23 ms
// cada 200 ms, y un broker que no responde, hasta 2 s). A cada lectura se le quita la línea de base (promedio lento,
// ~1 s), se rectifica y se suaviza (~100 ms): eso es la envolvente, que sube al contraer. Cada segundo se publica el
// RMS de la señal y el pico de la envolvente, en mV a la SALIDA del AD8232 (amplificada; no son microvoltios del
// músculo), y si los electrodos están puestos. Al pegarlos, el primer segundo no cuenta (la salida se acomoda).
int muscMuestrasSeg = 0;            // lecturas del último segundo (deberían ser 500), para el monitor serie
uint32_t muscMvAhora = 0;           // última lectura en mV y estado de LO+ y LO-, para revisar el cableado
bool loMasAhora = false, loMenosAhora = false;
// Del último segundo, para la prueba: lecturas con LO+ / LO- en alto, en el tope, y la salida mínima y máxima
int muscLoMasSeg = 0, muscLoMenosSeg = 0, muscTopeSeg = 0;
uint32_t muscMinSeg = 0, muscMaxSeg = 0;
volatile bool loMasVisto = false, loMenosVisto = false, topeVisto = false;  // desde la última vez que se dibujó

#if !MODO_SIMULADO
static_assert(pdMS_TO_TICKS(MUSCULO_CADA_MS) >= 1, "MUSCULO_CADA_MS es menor que un tick de FreeRTOS");
portMUX_TYPE candadoMusculo = portMUX_INITIALIZER_UNLOCKED;
float muscBase = NAN, muscEnv = 0;  // solo los usa la tarea
int muscAsentando = 0;
// Lo que va del segundo en curso: lo suma la tarea y lo resume (y pone en cero) calcularMusculo, con el candado
float muscSuma2 = 0, muscPico = 0;
int muscN = 0, muscDespegado = 0, muscBuenas = 0;
int muscLoMasN = 0, muscLoMenosN = 0, muscTopeN = 0;
uint32_t muscMin = UINT32_MAX, muscMax = 0;
// Filtros (solo los usa la tarea). La captura del 15/11 con la laptop enchufada: 72 % de la señal era 50 Hz y casi
// todo el resto, sus armónicos (100, 150, 200 y 250 Hz). Con pasa altos 10 Hz + notch 50 y 100 Hz + pasa bajos de
// 45 Hz (4.º orden), el 92 % de lo que queda está entre 10 y 45 Hz (lo único que deja pasar la placa del AD8232).
const float FS_MUSCULO = 1000.0f / MUSCULO_CADA_MS;
const float RED_HZ = MUSCULO_RED_HZ > 0 ? MUSCULO_RED_HZ : 50;
Biquad filtroAltos = pasaAltos(10, FS_MUSCULO), filtroRed = notch(RED_HZ, FS_MUSCULO, 4),
       filtroRed2 = notch(2 * RED_HZ, FS_MUSCULO, 4), filtroBajos = pasaBajos(45, FS_MUSCULO),
       filtroBajos2 = pasaBajos(45, FS_MUSCULO);

void leerMusculo() {
  bool loMas = digitalRead(PIN_LO_MAS) == HIGH, loMenos = digitalRead(PIN_LO_MENOS) == HIGH;
  uint32_t mvCrudo = analogReadMilliVolts(PIN_MUSCULO);  // con la calibración de fábrica de la placa
  float mv = mvCrudo;
  // Con ruido, LO+ y LO- dan pulsos de pocos ms aunque los electrodos estén bien: despegado = en alto 50 ms seguidos
  static int loMasSeguidas = 0, loMenosSeguidas = 0;
  const int SEGUIDAS = MUSCULO_DESPEGADO_MS / MUSCULO_CADA_MS;
  loMasSeguidas = loMas ? min(loMasSeguidas + 1, SEGUIDAS) : 0;
  loMenosSeguidas = loMenos ? min(loMenosSeguidas + 1, SEGUIDAS) : 0;
  bool despegadoMas = loMasSeguidas >= SEGUIDAS, despegadoMenos = loMenosSeguidas >= SEGUIDAS;
  bool despegado = despegadoMas || despegadoMenos;
#ifdef CRUDO_MUSCULO  // cada lectura por el monitor serie (500/s), para analizar el ruido en la laptop
  Serial.printf("c %lu %d %d\n", (unsigned long)mvCrudo, loMas, loMenos);
#endif
  bool cuenta = false;
  float ac = 0;
  if (despegado) {  // al volver a pegar el electrodo, los filtros se rehacen y se espera a que se asienten
    muscBase = NAN;
    muscEnv = 0;
    filtroAltos.reiniciar(), filtroRed.reiniciar(), filtroRed2.reiniciar();
    filtroBajos.reiniciar(), filtroBajos2.reiniciar();
    muscAsentando = MUSCULO_ASENTAR_MS / MUSCULO_CADA_MS;
  } else {
    if (isnan(muscBase)) muscBase = mv;  // se resta la primera lectura: así el pasa altos no arranca con un salto
    ac = filtroAltos.paso(mv - muscBase);  // desde 10 Hz: sin deriva ni movimiento lento
    if (MUSCULO_RED_HZ > 0) ac = filtroRed2.paso(filtroRed.paso(ac));  // sin el zumbido de la red (50 y 100 Hz)
    ac = filtroBajos2.paso(filtroBajos.paso(ac));  // hasta 45 Hz: fuera los armónicos de 150, 200 y 250 Hz
    muscEnv += MUSCULO_ENVOLVENTE * (fabsf(ac) - muscEnv);
    if (muscAsentando > 0) muscAsentando--;
    else cuenta = true;
  }
  portENTER_CRITICAL(&candadoMusculo);
  muscN++;
  if (despegado) muscDespegado++;
  if (cuenta) {
    muscBuenas++;
    muscSuma2 += ac * ac;
    muscPico = max(muscPico, muscEnv);
  }
  bool tope = mvCrudo >= MUSCULO_TOPE_MV || mvCrudo <= 100;
  muscLoMasN += loMas;
  muscLoMenosN += loMenos;
  muscTopeN += tope;
  muscMin = min(muscMin, mvCrudo);
  muscMax = max(muscMax, mvCrudo);
  muscMvAhora = mvCrudo;
  loMasAhora = loMas;
  loMenosAhora = loMenos;
  portEXIT_CRITICAL(&candadoMusculo);
  if (despegadoMas) loMasVisto = true;
  if (despegadoMenos) loMenosVisto = true;
  if (tope && !despegado) topeVisto = true;
#ifdef DEPURAR_MUSCULO  // para el Serial Plotter: señal y envolvente en mV, 1 de cada 5 lecturas (100/s)
  static int cada5 = 0;
  if (++cada5 >= 5) {
    cada5 = 0;
    Serial.printf("senal:%.0f envolvente:%.0f\n", ac, muscEnv);
  }
#endif
}

void tareaMusculo(void *) {
  TickType_t siguiente = xTaskGetTickCount();
  for (;;) {
    leerMusculo();
    vTaskDelayUntil(&siguiente, pdMS_TO_TICKS(MUSCULO_CADA_MS));
  }
}

void iniciarMusculo() {
  pinMode(PIN_LO_MENOS, INPUT);       // GPIO 35: solo entrada, sin resistencias internas
  pinMode(PIN_LO_MAS, INPUT_PULLUP);  // sin el AD8232 conectado da «despegado» en vez de un valor al azar
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_MUSCULO, ADC_11db);  // 0 a ~3,1 V
  // En el núcleo de loop() (1) con más prioridad que loop(): la interrumpe cada 2 ms unos microsegundos
  xTaskCreatePinnedToCore(tareaMusculo, "musculo", 4096, nullptr, 2, nullptr, 1);
}

// Una vez por segundo: resume el último segundo. Con los electrodos despegados la mitad del tiempo o más:
// electrodos = false. Con menos de medio segundo de señal asentada (recién pegados): RMS y pico en null.
void calcularMusculo() {
  portENTER_CRITICAL(&candadoMusculo);
  int n = muscN, despegadas = muscDespegado, buenas = muscBuenas;
  float suma2 = muscSuma2, pico = muscPico;
  muscLoMasSeg = muscLoMasN, muscLoMenosSeg = muscLoMenosN, muscTopeSeg = muscTopeN;
  muscMinSeg = n ? muscMin : 0, muscMaxSeg = muscMax;
  muscSuma2 = muscPico = 0;
  muscN = muscDespegado = muscBuenas = 0;
  muscLoMasN = muscLoMenosN = muscTopeN = 0;
  muscMin = UINT32_MAX, muscMax = 0;
  portEXIT_CRITICAL(&candadoMusculo);
  muscMuestrasSeg = n;
  electrodosOk = n > 0 && despegadas * 2 < n;
  bool hayValores = electrodosOk && buenas * 2 >= n;
  musculoRealRmsMv = musculoRmsMv = hayValores ? sqrtf(suma2 / buenas) : NAN;
  musculoRealPicoMv = musculoPicoMv = hayValores ? pico : NAN;
  if (FINGIR_MUSCULO && electrodosOk) fingirMusculo();  // electrodos reales; los valores publicados, fingidos
}
#else  // MODO_SIMULADO: sin AD8232, electrodos siempre puestos y valores fingidos
void iniciarMusculo() {}

void calcularMusculo() {
  muscMuestrasSeg = 1000 / MUSCULO_CADA_MS;
  electrodosOk = true;
  fingirMusculo();
}
#endif

// Valores fingidos (se publican con "musculo_simulado": true): suben mientras la prueba guiada dice APRIETA
void fingirMusculo() {
  musculoRmsMv = musculoApretando ? 200 + random(0, 80) : 15 + random(0, 10);
  musculoPicoMv = musculoRmsMv * (1.4f + random(0, 30) / 100.0f);
}

// Aviso de la OLED desde el último dibujo. nivel: 0 = bien, 1 = salida en el tope, 2 = electrodo despegado.
// Por la norma del ECG (derivación I): LO+ = LA (amarillo), LO- = RA (rojo); los dos a la vez suele ser RL (verde).
const char *avisoMusculo(int &nivel) {
  bool pierdeMas = loMasVisto, pierdeMenos = loMenosVisto, enTope = topeVisto;
  loMasVisto = loMenosVisto = topeVisto = false;
  nivel = pierdeMas || pierdeMenos ? 2 : enTope ? 1 : 0;
  return pierdeMas && pierdeMenos ? "Pierden 2: mira RL"
         : pierdeMas              ? "Pierde LA amarillo"
         : pierdeMenos            ? "Pierde RA rojo"
         : enTope                 ? "TOPE: aprieta electr."
                                  : "Senal OK";
}

// Largo de la barra de la OLED (0 a 1): la envolvente real, o la fingida
float maxEnvBarra = 100;
float barraMusculo() {
#if !MODO_SIMULADO
  if (!FINGIR_MUSCULO) {
    float env = isnan(muscEnv) ? 0 : muscEnv;
    maxEnvBarra = max(maxEnvBarra, env);
    return env / maxEnvBarra;
  }
#endif
  return musculoApretando ? 0.75f + random(0, 20) / 100.0f : 0.06f + random(0, 5) / 100.0f;
}

// Fase de la prueba guiada del músculo, debajo de la primera línea de la OLED: nombre, segundos, barra y aviso
void dibujarFaseMusculo(int f, int quedan, const char *aviso) {
  centrar(f >= 0 ? FASES_MUSCULO[f].nombre : "FIN", 2, 11);
  pantalla.setTextSize(3);
  pantalla.setCursor(0, 31);
  pantalla.printf("%2d", max(0, quedan));
  pantalla.setTextSize(1);
  pantalla.setCursor(44, 31);
  pantalla.print(f >= 0 ? FASES_MUSCULO[f].texto : "Otra vez en...");
  pantalla.drawRect(44, 42, 84, 8, SSD1306_WHITE);
  pantalla.fillRect(44, 42, (int)(84 * constrain(barraMusculo(), 0.0f, 1.0f)), 8, SSD1306_WHITE);
  pantalla.setCursor(0, 56);
  pantalla.print(aviso);
}

// ================================================================ prueba guiada del AD8232 (-DPRUEBA_MUSCULO=1)
// Solo el sensor de músculo, con los valores REALES (sin fingir): la misma secuencia de 35 s que en la evaluación,
// repetida (8 s de pausa entre vueltas). LED: verde = señal bien, rojo = electrodo despegado, amarillo = tope.
// Monitor serie: una línea por segundo con todo lo medido (con -DCRUDO_MUSCULO=1, además cada lectura).
#if PRUEBA_MUSCULO && !MODO_SIMULADO
const int PAUSA_PRUEBA_S = 8;
uint32_t inicioPrueba = 0, ultimoSegPrueba = 0, ultimoDibujoPrueba = 0;
int vueltaPrueba = 1;

void cuidarPrueba() {
  if (inicioPrueba == 0) inicioPrueba = millis();
  int quedan;
  uint32_t enFase, ms = millis() - inicioPrueba;
  int f = faseMusculo(ms, quedan, enFase);
  if (f < 0) {
    quedan = PAUSA_PRUEBA_S - (int)(enFase / 1000);
    if (quedan <= 0) {  // vuelve a empezar
      inicioPrueba = millis();
      vueltaPrueba++;
      ms = 0;
      f = faseMusculo(0, quedan, enFase);
    }
  }
  musculoApretando = f >= 0 && FASES_MUSCULO[f].aprieta && enFase >= 500;
  if (f != faseMusculoAntes) {
    faseMusculoAntes = f;
    if (f >= 0 && FASES_MUSCULO[f].aprieta) pitar(2, 120);
    else if (f >= 0 && strcmp(FASES_MUSCULO[f].nombre, "DESCANSA") == 0) pitar(1, 300);
    else if (f < 0) pitar(3, 80);
    Serial.printf("[prueba] vuelta %d fase %s\n", vueltaPrueba, f >= 0 ? FASES_MUSCULO[f].nombre : "FIN");
  }
  int seg = ms / 1000;
  if (millis() - ultimoSegPrueba >= 1000) {  // resumen del segundo (de 500 lecturas)
    ultimoSegPrueba = millis();
    calcularMusculo();
    Serial.printf("[prueba] t=%2d fase=%-9s lecturas=%d lo+=%d lo-=%d tope=%d salida=%lu..%lu mV rms=%.1f pico=%.1f\n",
                  seg, f >= 0 ? FASES_MUSCULO[f].nombre : "FIN", muscMuestrasSeg, muscLoMasSeg, muscLoMenosSeg,
                  muscTopeSeg, (unsigned long)muscMinSeg, (unsigned long)muscMaxSeg, musculoRmsMv, musculoPicoMv);
  }
  if (millis() - ultimoDibujoPrueba < CADA_PANTALLA_MS) return;
  ultimoDibujoPrueba = millis();
  int nivel;
  const char *aviso = avisoMusculo(nivel);
  escribirLed(nivel > 0, nivel < 2, false);  // verde, amarillo (tope) o rojo (despegado)
  if (!hayPantalla) return;
  pantalla.clearDisplay();
  pantalla.setTextColor(SSD1306_WHITE);
  pantalla.setTextSize(1);
  pantalla.setCursor(0, 0);
  pantalla.printf("AD8232 v%d   t=%ds", vueltaPrueba, seg);
  dibujarFaseMusculo(f, quedan, aviso);
  pantalla.display();
}
#endif

void loop() {
#if PRUEBA_MUSCULO && !MODO_SIMULADO
  cuidarZumbador();
  cuidarPrueba();
  return;
#endif
  cuidarWifi();
  cuidarMqtt();
#if !MODO_SIMULADO
  if (haySensor) leerSensor();
  cuidarMpu();
#endif
  cuidarMedicion();  // la secuencia guiada corre con red y sin red
  pitarCuenta();
  cuidarZumbador();
  if (millis() - ultimaPublicacion >= CADA_PUBLICAR_MS) {
    ultimaPublicacion = millis();
    calcularLecturas();
    calcularMusculo();
    guardarLectura();
    if (mqtt.connected()) publicarDatos();
  }
  if (millis() - ultimaPantalla >= CADA_PANTALLA_MS) {
    ultimaPantalla = millis();
    dibujarPantalla();
    // azul mientras no hay conexión; en modo local, en «repite» parpadea
    if (!colorSemaforo.length() || colorSemaforo == "repetir") mostrarColorEnLed();
  }
  if (millis() - ultimoResumen >= 5000) {
    ultimoResumen = millis();
    Serial.printf("[esp32] %s dedo=%d pulso=%.1f hrv=%.1f spo2=%.0f mov=%.3f calidad=%.2f wifi=%d mqtt=%d\n",
                  persona.c_str(), dedo, pulsoLpm, hrvMs, spo2, movimiento, calidad, WiFi.status() == WL_CONNECTED,
                  mqtt.connected());
    // AD8232: lecturas del último segundo (500), LO+ y LO- (1 = despegado) y la salida ahora (~1650 mV en reposo)
    // (real = medido de verdad; publicado = lo que va por MQTT, fingido con MUSCULO_FINGIDO)
    Serial.printf("[esp32] musculo electrodos=%d real rms=%.1f pico=%.1f | publicado rms=%.1f pico=%.1f mV "
                  "lecturas/s=%d lo+=%d lo-=%d salida=%lu mV\n",
                  electrodosOk, musculoRealRmsMv, musculoRealPicoMv, musculoRmsMv, musculoPicoMv, muscMuestrasSeg,
                  loMasAhora, loMenosAhora, (unsigned long)muscMvAhora);
  }
}
