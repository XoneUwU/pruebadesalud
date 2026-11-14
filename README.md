# ¿Está apto hoy? — Sistema (parte de IA)

NASA Space Apps Challenge 2026 · Reto «Create Health Monitoring Software for Astronauts on Space Missions».

Esta carpeta es la base del repositorio común. Ya incluye los módulos de **Bri** (voz y copiloto), los
paneles web, la conexión MQTT que usan todos, la configuración de Mosquitto, un simulador y los scripts de Windows.

```
apto-hoy/
├── config.env            IP del broker, usuario y opciones (todos los módulos lo leen)
├── instalar.bat          instala todo (una sola vez)
├── iniciar.bat           arranca el sistema completo en la laptop de Bri
├── comun/                configuración y cliente MQTT común  ← úsenlo en sus módulos
├── voz/                  análisis de fatiga en la voz (Bri)
├── copiloto/             copiloto por voz: Whisper + Ollama + fichas + Piper (Bri)
│   └── protocolos.md     fichas que el copiloto usa para responder
├── paneles/              paneles web: estación, tripulación y Tierra (servidor.py, sin internet)
├── coordinador/          coordinador_provisional.py, hasta que esté el de Danilo
├── registrador/          guarda todo apto/# en MongoDB, exporta a CSV y reproduce sesiones
├── herramientas/         simulador.py (datos falsos) y escuchar.py (ver mensajes)
├── mosquitto/            configuración del broker (evento y desarrollo)
├── firmware/  vision/    ← carpetas del resto del equipo
└── datos/                grabaciones e historial (no se sube a Git)
```

## 1. Instalar (laptop de Bri, una vez)

1. Instalar **Python 3.11 o 3.12** (marcar «Add to PATH»; no usar versiones más nuevas), **Ollama** (ollama.com),
   **Mosquitto** (mosquitto.org) y **MongoDB Community Server** (mongodb.com; el registrador lo arranca solo, no
   hace falta su servicio de Windows).
2. Doble clic en `instalar.bat`. Descarga librerías, la voz en español de Piper, `qwen2.5:7b` y Whisper.

## 2. Probar hoy, paso a paso

Abrir una terminal en la carpeta del proyecto (`.venv\Scripts\activate` primero).

| Paso | Comando | Qué deberías ver |
|---|---|---|
| Broker | `"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto\mosquitto-dev.conf -v` | «mosquitto running» |
| Ver mensajes | `python herramientas\escuchar.py` | «Escuchando apto/#» |
| Voz sin micrófono | `python voz\voz_fatiga.py --listar` | La lista de micrófonos |
| Voz con micrófono | `python voz\voz_fatiga.py --persona bri` | Rasgos de tu voz y el mensaje en escuchar.py |
| Copiloto escrito | `python copiloto\copiloto.py --texto` | Responde y habla |
| Simulador | `python herramientas\simulador.py` y luego `2` | El copiloto lee el resultado amarillo en voz alta |
| Copiloto por voz | `python copiloto\copiloto.py` y Enter vacío | Te escucha, transcribe y responde |
| Paneles web | `python paneles\servidor.py` y abrir http://localhost:8080 | Estación, tripulación y Tierra (ver la sección 5) |
| Coordinador provisional | `python coordinador\coordinador_provisional.py` | Calcula el semáforo al terminar el cuestionario de la estación (sección 6) |
| Registrador | `python registrador\mongo_local.py` y `python registrador\registrador.py` | Guarda cada mensaje en MongoDB (sección 7) |
| Todo junto | `iniciar.bat dev` | Una ventana por módulo: broker, MongoDB, registrador, voz, copiloto, coordinador provisional y paneles |

Opciones útiles del copiloto: `--sin-llm` (sin Ollama, responde con las fichas), `--sin-voz` (solo texto),
`--sin-auto` (no lee cada evaluación nueva). Muestra cuánto tarda Whisper y el modelo: la meta es menos de 5 s.

Si el copiloto responde lento: en `config.env` cambien `WHISPER_MODEL=base`, o usen un modelo más chico en
Ollama (`ollama pull qwen2.5:3b` y `OLLAMA_MODEL=qwen2.5:3b`).

## 3. Modo evento (con usuarios)

1. `mosquitto\crear_usuarios.bat` → crea `sistema` (publica y lee) y `equipo` (solo lee).
2. En `config.env`: `MQTT_HOST` = IP de la laptop de Bri, `MQTT_USER=sistema` y su clave, y
   `MQTT_USER_LECTURA=equipo` y su clave (los usan los paneles abiertos desde otras laptops).
3. Firewall, en PowerShell como administrador:
   ```
   Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
   New-NetFirewallRule -DisplayName "Apto hoy" -Direction Inbound -Protocol TCP -LocalPort 1883,9001,8080 -Action Allow -Profile Private
   ```
4. Si el servicio de Mosquitto de Windows está activo, detenerlo: `net stop mosquitto` (como administrador).
5. `iniciar.bat` arranca el broker, MongoDB y el registrador, la voz (`--servicio`), el copiloto, el
   coordinador provisional y el servidor de los paneles, cada uno en su ventana.
6. En la laptop de Bri: http://localhost:8080/estacion.html. En el proyector y las otras laptops (misma red):
   http://IP-de-Bri:8080/tripulacion.html y http://IP-de-Bri:8080/tierra.html.

## 4. Temas MQTT

Todo mensaje es JSON y lleva `persona`, `sesion` y `ts`. `control` es un nombre reservado: ninguna persona puede llamarse así.

| Tema | Publica | Lee | Contenido |
|---|---|---|---|
| `apto/control/sesion` | Panel (Sebas), copiloto | Todos | `{"persona", "tarea", "sesion"}`: inicio de una evaluación y persona activa. La estación lo publica al tocar «Comenzar» (`sesion` = `20261113-193005-bri`). El copiloto lo publica cuando alguien dice «soy Erick», «habla Sebas» o «aquí Bri» (nombres de `TRIPULACION` en `config.env`). |
| `apto/control/modulos/{modulo}` | Todos los módulos de Python (`comun/mqtt_cliente.py`) | Estación | `{"modulo", "activo": true}` al conectarse, **con retain**; el Last Will publica `{"activo": false}` si el programa se cae, y `cerrar()` lo publica al salir bien. La estación espera los nombres `voz`, `copiloto`, `vision` y `coordinador`. Son cuatro niveles a propósito: `apto/estado/{modulo}` coincidiría con `apto/+/voz`. |
| `apto/control/orden_vision` | Panel (Sebas) | Visión | `{"accion": "medir", "persona", "segundos": 60, "sesion"}`: la estación pide un minuto de medición con la cámara (la estación no abre la cámara: lo hace el módulo de visión, que muestra el rostro en su ventana) |
| `apto/control/estado_vision` | Visión | Panel | `{"persona", "estado": "midiendo" o "listo"}` |
| `apto/control/orden_voz` | Panel (Sebas) | Voz | `{"accion": "grabar", "persona", "segundos", "linea_base", "sesion"}` |
| `apto/control/estado_voz` | Voz | Panel | `{"persona", "estado": "grabando" o "listo"}` |
| `apto/control/pregunta` | Panel (Sebas) | Copiloto | `{"persona", "pregunta", "sesion"}`: pregunta escrita desde la estación |
| `apto/{persona}/esp32` | ESP32 (Adrian) | Coordinador | Pulso, HRV, SpO₂, movimiento, sueño |
| `apto/{persona}/vision` | Visión (Erick) | Coordinador | Pulso por cámara, parpadeo, PERCLOS. Con `sesion` de la orden. El coordinador provisional usa `perclos` como fracción de 0 a 1 (acepta también porcentaje) |
| `apto/{persona}/voz` | Voz (Bri) | Coordinador | Tono, jitter, shimmer, HNR, pausas. Con 3 o más mediciones de línea base, también `z_rasgos`, `indice_cansancio` (positivo = más cansancio), `estado_voz` y `motivos_voz` (frases neutras). Es una sugerencia, no un diagnóstico. |
| `apto/{persona}/pvt` | PVT (Sebas) | Coordinador | PVT-B en el navegador: `rt_media_ms`, `rt_mediana_ms`, `lapsos` (355 ms o más, o sin respuesta en 30 s), `anticipadas` (antes del estímulo o en menos de 100 ms), `lapsos_por_min` y `anticipadas_por_min` (para comparar 3 min con 1 min), `n_estimulos`, `duracion_s`, `linea_base`, `modo_demo` (true = 1 minuto) |
| `apto/{persona}/dsst` | Panel (Sebas) | Coordinador | Prueba de símbolos (DSST, 90 s, opcional): `correctas`, `incorrectas`, `por_minuto` (correctas por minuto), `duracion_s`, `linea_base` || `apto/{persona}/cuestionario` | Panel (Sebas) | Coordinador | `kss` (escala de somnolencia de Karolinska, 1 a 9), `kss_texto`, `horas_sueno` (de 0 a 16, de media en media hora), `linea_base` |
| `apto/{persona}/evaluacion` | Coordinador (Danilo; por ahora el provisional) | Paneles, copiloto | `color`, `puntaje`, `motivos`, `accion`, `pesos` y `sesion` (la de la estación, para que la estación lo reconozca). El provisional agrega `"provisional": true` y `senales` (puntos por fuente). **Publicar con retain.** Los `motivos` se escriben como frases neutras, sin sujeto («Menos horas de sueño de lo habitual», no «Durmió menos»), porque el copiloto los lee después de «tu resultado… Motivos:». |
| `apto/{persona}/semaforo` | Coordinador | ESP32 | Solo `color`. **Con retain.** |
| `apto/{persona}/copiloto` | Copiloto (Bri) | Paneles | `pregunta`, `respuesta`, `fichas`, `modo` |

## 5. Paneles web

`python paneles\servidor.py` sirve las páginas en el puerto 8080 de toda la red y genera `/config.js` desde
`config.env`. Las páginas son HTML y JavaScript sin frameworks y se conectan al broker por WebSocket (puerto
`MQTT_WS_PORT`, 9001) en el mismo host desde el que se abrieron. **No usan internet**: la librería MQTT
(mqtt.js 5.16.1) está en `paneles/web/vendor/` y no hay CDN ni fuentes externas.

| Página | Para qué | Quién la usa |
|---|---|---|
| http://localhost:8080/estacion.html | La evaluación paso a paso: qué módulos están abiertos, persona y tarea, dispositivo (pulso, HRV, SpO₂ en vivo), cámara (60 s, la mide el módulo de visión), voz (frase de `voz_fatiga.py`), prueba de reacción PVT-B (3 min, o 1 min con «Modo demo»), prueba de símbolos DSST (90 s, opcional), cuestionario de Karolinska y resultado con el semáforo y el copiloto | La persona que se evalúa, en la laptop de Bri (pantalla completa con ⛶) |
| http://IP-de-Bri:8080/tripulacion.html | Una tarjeta por integrante, la recomendación para la tarea (la misma de `resumen_tripulacion()` del copiloto) y las últimas respuestas del copiloto | Proyector y otras laptops (solo lectura) |
| http://IP-de-Bri:8080/tierra.html | Las evaluaciones llegan con `RETRASO_TIERRA_S` de retraso: se ve que la tripulación decidió antes de que Tierra se enterara | Control de misión (solo lectura) |

- **Credenciales**: si la página se abre en la misma laptop (localhost), `/config.js` lleva `MQTT_USER` y
  `MQTT_PASS` (puede publicar). Desde otra laptop lleva `MQTT_USER_LECTURA` y `MQTT_PASS_LECTURA` (solo lee).
  Por eso la estación solo funciona en la laptop de Bri. En desarrollo todos quedan vacíos.
- **Opciones** en `config.env`: `PVT_SEGUNDOS` (180 = PVT-B de 3 minutos; la casilla «Modo demo» de la estación
  la baja a 1 minuto y lo anota como `modo_demo: true`), `RETRASO_TIERRA_S` (20 s), `MQTT_WS_PORT` (9001) y
  `TRIPULACION` (los botones de la estación y las tarjetas). Si se cambian, hay que reiniciar `servidor.py`.
- **Módulos que faltan**: al inicio, la estación muestra si están abiertos voz, copiloto, visión y coordinador
  (`apto/control/modulos/+`). En cada paso dice «el módulo X no está abierto» y cómo abrirlo, en vez de esperar.
  El ESP32 no es un módulo de Python: si en 10 s no llegan datos, la estación lo avisa.
- Cada página muestra si está conectada al broker. Los datos con `"simulado": true` llevan la etiqueta SIMULADO, y
  los del coordinador provisional, PROVISIONAL.
- **Atajo para probar** una pantalla de la estación sin hacer todo el recorrido:
  `estacion.html?paso=reaccion&persona=bri&demo=1` (pasos: dispositivo, camara, voz, reaccion, simbolos,
  cuestionario, resultado; `&dsst=1` agrega los símbolos). No publica la sesión.
- **Prueba**: `python paneles\pruebas_paneles.py` (servidor, `/config.js`, que no se salga de `paneles/web`, sin
  recursos externos, `node --check` y la recomendación comparada con la del copiloto).

## 6. Coordinador provisional (hasta que esté el de Danilo)

`python coordinador\coordinador_provisional.py` (lo arranca `iniciar.bat`). Cuando la estación publica el
cuestionario (su último paso), junta los datos de esa sesión (reacción, símbolos, cuestionario, voz y visión si
llegan) y publica en `apto/{persona}/evaluacion` y `apto/{persona}/semaforo`, con retain y `"provisional": true`.
Si después llega otro dato de la misma sesión, vuelve a calcular.

Reglas (detalle y umbrales al inicio del archivo): cada indicador da 0, 1 o 2 puntos. Con línea base se compara
con el promedio de la persona (`datos/coordinador/linea_base.jsonl`); sin línea base, con valores fijos de
referencia del prototipo, que hay que calibrar. **Rojo** si alguna fuente tiene 2 puntos o si 3 fuentes tienen
puntos; **amarillo** si alguna tiene puntos; **verde** si ninguna. Los motivos son frases neutras, sin sujeto
(«Somnolencia alta según la escala de Karolinska»). La voz pesa como máximo 1 punto, porque es una señal débil.

**Cómo lo reemplaza Danilo:**
1. Crear `coordinador\coordinador.py` con `ClienteMQTT("coordinador")`: con ese nombre la estación lo ve como
   «Coordinador activo» (`apto/control/modulos/coordinador`).
2. Leer los mismos temas y publicar `apto/{persona}/evaluacion` con retain y con el contrato de la tabla de la
   sección 4: `color`, `puntaje`, `motivos` (frases neutras), `accion` y la `sesion` de la estación. Sin
   `provisional`.
3. En `iniciar.bat`, poner `rem` a la línea del provisional y quitárselo a la de `coordinador.py`. Nunca deben
   correr los dos a la vez: publicarían dos resultados distintos para la misma sesión.
4. `coordinador_provisional.py` y `pruebas_coordinador.py` pueden quedar como referencia.

## 7. Registrador (MongoDB)

Guarda cada mensaje de `apto/#` para validar el sistema después y como respaldo de la demo.

- **MongoDB solo en esta laptop**: `registrador\mongo_local.py` arranca el `mongod` ya instalado como un
  programa normal (sin servicio ni administrador), escuchando **solo en 127.0.0.1**, con los datos en
  `datos\mongo`. Si el puerto de `MONGO_URI` ya está ocupado, no arranca otro y avisa. `config.env`:
  `MONGO_URI=mongodb://localhost:27017` y `MONGO_DB=apto_hoy` (y `MONGOD_EXE` si `mongod` está en otra carpeta).
- **`registrador.py`** guarda en la colección `mensajes`
  `{recibido (fecha), tema, persona, tipo, simulado, reproducido, datos: <el JSON original>}`, con índices por
  `(persona, tipo, recibido)` y por `tipo`. En `apto/control/...` el tipo es `control/sesion`, `control/modulos`,
  etc., y la persona sale del mensaje si la trae. Los mensajes retenidos que el broker entrega al conectarse no se
  guardan otra vez.
- **Si MongoDB no responde, no se pierde nada**: los mensajes van a `datos\pendientes_mongo.jsonl` y se suben solos
  cuando Mongo vuelve (cada línea lleva su `_id`, así un reintento nunca duplica).
- **`exportar.py`**: un CSV por tipo en `datos\exportes` (`--tipo`, `--persona`, `--desde`, `--hasta`,
  `--solo-reales` sin simulados ni reproducidos, `--excel` con `;` y coma decimal).
- **`reproducir.py`**: vuelve a publicar una sesión respetando los tiempos (`--velocidad`, `--max-espera`), con
  `"reproducido": true`, `ts` de ahora y `ts_original`. `--sesiones` lista las sesiones guardadas de una persona.
  Reproduce los datos, la evaluación y el semáforo (con retain), el copiloto y la sesión; **no** reproduce órdenes
  ni preguntas, que harían grabar o responder de verdad a los módulos. El coordinador ignora lo reproducido.
- Alternativa con Docker (si Docker Desktop está abierto):
  `docker run -d --name apto-mongo -p 127.0.0.1:27017:27017 -v apto-mongo:/data/db mongo:8`. El `127.0.0.1:`
  es lo que impide que se abra a la red. En la laptop de Bri no se usa porque la máquina virtual de Docker ocupa
  unos 2 GB de RAM que necesitan Ollama y Whisper.

## 8. Reglas para sumar un módulo (todo el equipo)

1. Cada módulo vive en su carpeta, con `requirements.txt` y un README con el comando para correrlo.
2. Usen `comun/mqtt_cliente.py`; nunca escriban la IP ni claves en el código (van en `config.env`). Así el
   módulo avisa solo si está abierto (`ClienteMQTT("vision")` → `apto/control/modulos/vision`).
3. En casa: Mosquitto propio con `mosquitto\mosquitto-dev.conf` y `MQTT_HOST=localhost`.
4. Prueben con `herramientas\simulador.py` y `herramientas\escuchar.py` sin esperar a los demás.
5. El ESP32 se conecta con el usuario `sistema` y su clave, a la IP de Bri, puerto 1883.

## Avisos

- Las fichas de `copiloto/protocolos.md` son una guía interna del prototipo: revísenlas y agreguen fuentes antes de presentar.
- Es un prototipo de apoyo a la decisión, no un dispositivo médico, y no diagnostica.
- Este código se desarrolló con ayuda de IA (Claude); el equipo lo revisó y probó.
