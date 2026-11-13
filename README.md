# ¿Está apto hoy? — Sistema (parte de IA)

NASA Space Apps Challenge 2026 · Reto «Create Health Monitoring Software for Astronauts on Space Missions».

Esta carpeta es la base del repositorio común. Ya incluye los módulos de **Xone** (voz y copiloto), la
conexión MQTT que usan todos, la configuración de Mosquitto, un simulador y los scripts de Windows.

```
apto-hoy/
├── config.env            IP del broker, usuario y opciones (todos los módulos lo leen)
├── instalar.bat          instala todo (una sola vez)
├── iniciar.bat           arranca el sistema completo en la laptop de Xone
├── comun/                configuración y cliente MQTT común  ← úsenlo en sus módulos
├── voz/                  análisis de fatiga en la voz (Xone)
├── copiloto/             copiloto por voz: Whisper + Ollama + fichas + Piper (Xone)
│   └── protocolos.md     fichas que el copiloto usa para responder
├── herramientas/         simulador.py (datos falsos) y escuchar.py (ver mensajes)
├── mosquitto/            configuración del broker (evento y desarrollo)
├── firmware/  vision/  coordinador/  paneles/     ← carpetas del resto del equipo
└── datos/                grabaciones e historial (no se sube a Git)
```

## 1. Instalar (laptop de Xone, una vez)

1. Instalar **Python 3.11 o 3.12** (marcar «Add to PATH»; no usar versiones más nuevas), **Ollama** (ollama.com) y **Mosquitto** (mosquitto.org).
2. Doble clic en `instalar.bat`. Descarga librerías, la voz en español de Piper, `qwen2.5:7b` y Whisper.

## 2. Probar hoy, paso a paso

Abrir una terminal en la carpeta del proyecto (`.venv\Scripts\activate` primero).

| Paso | Comando | Qué deberías ver |
|---|---|---|
| Broker | `"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto\mosquitto-dev.conf -v` | «mosquitto running» |
| Ver mensajes | `python herramientas\escuchar.py` | «Escuchando apto/#» |
| Voz sin micrófono | `python voz\voz_fatiga.py --listar` | La lista de micrófonos |
| Voz con micrófono | `python voz\voz_fatiga.py --persona xone` | Rasgos de tu voz y el mensaje en escuchar.py |
| Copiloto escrito | `python copiloto\copiloto.py --texto` | Responde y habla |
| Simulador | `python herramientas\simulador.py` y luego `2` | El copiloto lee el resultado amarillo en voz alta |
| Copiloto por voz | `python copiloto\copiloto.py` y Enter vacío | Te escucha, transcribe y responde |

Opciones útiles del copiloto: `--sin-llm` (sin Ollama, responde con las fichas), `--sin-voz` (solo texto),
`--sin-auto` (no lee cada evaluación nueva). Muestra cuánto tarda Whisper y el modelo: la meta es menos de 5 s.

Si el copiloto responde lento: en `config.env` cambien `WHISPER_MODEL=base`, o usen un modelo más chico en
Ollama (`ollama pull qwen2.5:3b` y `OLLAMA_MODEL=qwen2.5:3b`).

## 3. Modo evento (con usuarios)

1. `mosquitto\crear_usuarios.bat` → crea `sistema` (publica y lee) y `equipo` (solo lee).
2. En `config.env`: `MQTT_HOST` = IP de la laptop de Xone, `MQTT_USER=sistema` y su clave.
3. Firewall, en PowerShell como administrador:
   ```
   Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
   New-NetFirewallRule -DisplayName "Apto hoy" -Direction Inbound -Protocol TCP -LocalPort 1883,9001,8080 -Action Allow -Profile Private
   ```
4. Si el servicio de Mosquitto de Windows está activo, detenerlo: `net stop mosquitto` (como administrador).
5. `iniciar.bat` arranca el broker, la voz y el copiloto, cada uno en su ventana.

## 4. Temas MQTT

Todo mensaje es JSON y lleva `persona`, `sesion` y `ts`. `control` es un nombre reservado: ninguna persona puede llamarse así.

| Tema | Publica | Lee | Contenido |
|---|---|---|---|
| `apto/control/sesion` | Panel (Sebas) | Todos | `{"persona", "tarea"}`: inicio de una evaluación y persona activa |
| `apto/control/orden_voz` | Panel (Sebas) | Voz | `{"accion": "grabar", "persona", "segundos", "linea_base"}` |
| `apto/control/estado_voz` | Voz | Panel | `{"persona", "estado": "grabando" o "listo"}` |
| `apto/control/pregunta` | Panel (Sebas) | Copiloto | `{"persona", "pregunta"}`: pregunta escrita desde la interfaz |
| `apto/{persona}/esp32` | ESP32 (Diego) | Coordinador | Pulso, HRV, SpO₂, movimiento, sueño |
| `apto/{persona}/vision` | Visión (Eric) | Coordinador | Pulso por cámara, parpadeo, PERCLOS |
| `apto/{persona}/voz` | Voz (Xone) | Coordinador | Tono, jitter, shimmer, HNR, pausas |
| `apto/{persona}/pvt` | PVT (Sebas) | Coordinador | Reacción media, lapsos, anticipadas |
| `apto/{persona}/cuestionario` | Panel (Sebas) | Coordinador | Escala de Karolinska, horas de sueño |
| `apto/{persona}/evaluacion` | Coordinador (Danilo) | Paneles, copiloto | `color`, `puntaje`, `motivos`, `accion`, `pesos`. **Publicar con retain.** |
| `apto/{persona}/semaforo` | Coordinador | ESP32 | Solo `color`. **Con retain.** |
| `apto/{persona}/copiloto` | Copiloto (Xone) | Paneles | `pregunta`, `respuesta`, `fichas`, `modo` |

## 5. Reglas para sumar un módulo (todo el equipo)

1. Cada módulo vive en su carpeta, con `requirements.txt` y un README con el comando para correrlo.
2. Usen `comun/mqtt_cliente.py`; nunca escriban la IP ni claves en el código (van en `config.env`).
3. En casa: Mosquitto propio con `mosquitto\mosquitto-dev.conf` y `MQTT_HOST=localhost`.
4. Prueben con `herramientas\simulador.py` y `herramientas\escuchar.py` sin esperar a los demás.
5. El ESP32 se conecta con el usuario `sistema` y su clave, a la IP de Xone, puerto 1883.

## Avisos

- Las fichas de `copiloto/protocolos.md` son una guía interna del prototipo: revísenlas y agreguen fuentes antes de presentar.
- Es un prototipo de apoyo a la decisión, no un dispositivo médico, y no diagnostica.
- Este código se desarrolló con ayuda de IA (Claude); el equipo lo revisó y probó.
