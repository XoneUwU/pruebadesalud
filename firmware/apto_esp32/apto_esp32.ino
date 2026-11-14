// «¿Está apto hoy?» — ESP32: pulso, HRV (RMSSD), SpO2 y movimiento; semáforo en LED RGB, OLED y zumbador.
//
//   publica  apto/{persona}/esp32           cada 1 s: persona, sesion, pulso_lpm, hrv_rmssd_ms, spo2, dedo,
//                                           movimiento, calidad (y "simulado": true con MODO_SIMULADO)
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

#if __has_include("secrets.h")
#include "secrets.h"
#else
#error "Falta secrets.h: copien secrets.ejemplo.h como secrets.h (misma carpeta) y pongan el Wi-Fi y la IP del broker."
#endif

#if !MODO_SIMULADO
#include "MAX30105.h"        // SparkFun MAX3010x (sirve para el MAX30102)
#include "heartRate.h"       // checkForBeat
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

uint32_t ultimoIntentoWifi = 0;
uint32_t ultimoIntentoMqtt = 0;
uint32_t ultimaPublicacion = 0;
uint32_t ultimaPantalla = 0;
uint32_t ultimoResumen = 0;
bool horaPedida = false;

// ================================================================ utilidades
void escribirLed(bool r, bool g, bool b) {
  bool encendido = LED_ANODO_COMUN ? LOW : HIGH;
  digitalWrite(PIN_LED_R, r ? encendido : !encendido);
  digitalWrite(PIN_LED_G, g ? encendido : !encendido);
  digitalWrite(PIN_LED_B, b ? encendido : !encendido);
}

void mostrarColorEnLed() {
  if (colorSemaforo == "verde") escribirLed(false, true, false);
  else if (colorSemaforo == "amarillo") escribirLed(true, true, false);
  else if (colorSemaforo == "rojo") escribirLed(true, false, false);
  else if (!mqtt.connected()) escribirLed(false, false, true);  // azul: sin conexión al broker
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

void pitar(int veces) {
  pitidosPendientes = veces;
  zumbando = false;
  proximoCambioZumbador = millis();
}

void cuidarZumbador() {
  if (pitidosPendientes == 0 || millis() < proximoCambioZumbador) return;
  zumbando = !zumbando;
  digitalWrite(PIN_ZUMBADOR, zumbando ? HIGH : LOW);
  if (!zumbando) pitidosPendientes--;
  proximoCambioZumbador = millis() + 150;
}

// ================================================================ semáforo y persona
void ponerSemaforo(const String &color) {
  if (color == "rojo" && colorSemaforo != "rojo") pitar(3);  // solo al pasar a rojo, no en cada reconexión
  colorSemaforo = color;
  mostrarColorEnLed();
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

void alMensaje(char *tema, byte *carga, unsigned int largo) {
  String t(tema);  // copia: el buffer de PubSubClient se reutiliza
  JsonDocument doc;
  if (deserializeJson(doc, carga, largo)) return;
  if (t == TEMA_SESION) {
    const char *p = doc["persona"] | "";
    if (personaValida(p) && persona != p) cambiarPersona(p);
    sesion = String((const char *)(doc["sesion"] | ""));
  } else if (t == temaSemaforo) {
    String color = doc["color"] | "";
    if (color == "verde" || color == "amarillo" || color == "rojo") ponerSemaforo(color);
  }
}

// ================================================================ Wi-Fi y MQTT (sin bloquear)
void cuidarWifi() {
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
    if (!dedo) continue;
    if (checkForBeat(ir)) alLatir(ahoraSensor());
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
  pulsoLpm = 72 + 4 * sinf(t / 20) + random(-10, 11) / 10.0f;
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
  ponerNumero(doc, "pulso_lpm", dedo ? pulsoLpm : NAN, 1);
  ponerNumero(doc, "hrv_rmssd_ms", dedo ? hrvMs : NAN, 1);
  ponerNumero(doc, "spo2", dedo ? spo2 : NAN, 0);
  doc["dedo"] = dedo;
  ponerNumero(doc, "movimiento", movimiento, 3);
  ponerNumero(doc, "calidad", calidad, 2);
  if (MODO_SIMULADO) doc["simulado"] = true;
  char ts[25];
  if (horaIso(ts, sizeof(ts))) doc["ts"] = ts;
  doc["fuente"] = "esp32";
  char buf[512];
  size_t n = serializeJson(doc, buf, sizeof(buf));
  mqtt.publish(temaDatos.c_str(), (const uint8_t *)buf, n, false);
}

void dibujarPantalla() {
  if (!hayPantalla) return;
  pantalla.clearDisplay();
  pantalla.setTextColor(SSD1306_WHITE);
  pantalla.setTextSize(2);
  pantalla.setCursor(0, 0);
  pantalla.print(nombreBonito(persona));
  pantalla.setTextSize(1);
  if (MODO_SIMULADO) {
    pantalla.setCursor(110, 0);
    pantalla.print("SIM");
  }
  pantalla.setCursor(0, 20);
  if (!dedo) pantalla.print("Pon el dedo");
  else if (isnan(pulsoLpm)) pantalla.print("Pulso: midiendo...");
  else pantalla.printf("Pulso: %.0f lpm", pulsoLpm);
  pantalla.setCursor(0, 31);
  if (dedo && !isnan(spo2)) pantalla.printf("SpO2: %.0f %%", spo2);
  else pantalla.print("SpO2: --");
  if (dedo && !isnan(hrvMs)) {
    pantalla.setCursor(74, 31);
    pantalla.printf("HRV %.0f", hrvMs);
  }
  pantalla.setCursor(0, 43);
  String c = colorSemaforo.length() ? colorSemaforo : String("-");
  c.toUpperCase();
  pantalla.print("Semaforo: ");
  pantalla.print(c);
  pantalla.setCursor(0, 56);
  pantalla.print(WiFi.status() == WL_CONNECTED ? "WiFi OK" : "WiFi --");
  pantalla.setCursor(64, 56);
  pantalla.print(mqtt.connected() ? "MQTT OK" : "MQTT --");
  pantalla.display();
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
  escribirLed(false, false, true);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(400000);
  Wire.beginTransmission(DIR_OLED);
  hayPantalla = Wire.endTransmission() == 0 && pantalla.begin(SSD1306_SWITCHCAPVCC, DIR_OLED);
  Serial.printf("[esp32] OLED: %s\n", hayPantalla ? "si" : "no encontrada");
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
}

void loop() {
  cuidarWifi();
  cuidarMqtt();
#if !MODO_SIMULADO
  if (haySensor) leerSensor();
  cuidarMpu();
#endif
  cuidarZumbador();
  if (millis() - ultimaPublicacion >= CADA_PUBLICAR_MS) {
    ultimaPublicacion = millis();
    calcularLecturas();
    if (mqtt.connected()) publicarDatos();
  }
  if (millis() - ultimaPantalla >= CADA_PANTALLA_MS) {
    ultimaPantalla = millis();
    dibujarPantalla();
    if (!colorSemaforo.length()) mostrarColorEnLed();  // azul mientras no hay conexión
  }
  if (millis() - ultimoResumen >= 5000) {
    ultimoResumen = millis();
    Serial.printf("[esp32] %s dedo=%d pulso=%.1f hrv=%.1f spo2=%.0f mov=%.3f calidad=%.2f wifi=%d mqtt=%d\n",
                  persona.c_str(), dedo, pulsoLpm, hrvMs, spo2, movimiento, calidad, WiFi.status() == WL_CONNECTED,
                  mqtt.connected());
  }
}
