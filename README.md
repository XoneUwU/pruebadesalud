# Prueba de salud 


Repositorio común del equipo: todos los módulos (ver «Equipo»), la conexión MQTT que usan todos, la configuración
de Mosquitto, un simulador y los scripts de Windows.

## Equipo

| Integrante | Módulo |
|---|---|
| **Bri** | Voz (fatiga en la voz) y copiloto por voz; la laptop de la estación (broker e integración) |
| **Danilo** | Coordinador (calcula el semáforo); mientras tanto corre el coordinador provisional |
| **Sebas** | Paneles (estación, tripulación y Tierra) y prueba de reacción (PVT) |
| **Erick** | Visión (cámara: pulso sin contacto, parpadeos, PERCLOS y bostezos) |
| **Adrian** | ESP32 (firmware: pulso, HRV, SpO2, movimiento y semáforo) |

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
├── vision/               pulso sin contacto, parpadeos y PERCLOS por cámara (MediaPipe)
├── firmware/             ESP32 (apto_esp32): pulso, HRV, SpO2, movimiento y semáforo (ver firmware/README.md)
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
| Simulador del ESP32 | `python herramientas\simulador.py --esp32 40 --spo2 89` | 40 lecturas del ESP32 (1 por segundo); con SpO2 bajo, la evaluación lleva el aviso de oxígeno |
| Copiloto por voz | `python copiloto\copiloto.py` y Enter vacío | Te escucha, transcribe y responde |
| Paneles web | `python paneles\servidor.py` y abrir http://localhost:8080 | Estación, tripulación y Tierra (ver la sección 5) |
| Coordinador provisional | `python coordinador\coordinador_provisional.py` | Calcula el semáforo al terminar el cuestionario de la estación (sección 6) |
| Registrador | `python registrador\mongo_local.py` y `python registrador\registrador.py` | Guarda cada mensaje en MongoDB (sección 7) |
| Visión | `python vision\vision.py --ver` (vista previa) o `--persona bri` (una medición) | Malla del rostro, regiones del pulso, pulso y EAR en vivo (sección 8) |
| Todo junto | `iniciar.bat dev` | Una ventana por módulo: broker, MongoDB, registrador, voz, copiloto, coordinador provisional, visión y paneles |

Opciones útiles del copiloto: `--sin-llm` (sin Ollama, responde con las fichas), `--sin-voz` (solo texto),
`--sin-auto` (no lee cada evaluación nueva). Muestra cuánto tarda Whisper y el modelo: la meta es menos de 5 s.

Si el copiloto responde lento: en `config.env` cambien `WHISPER_MODEL=base`, o usen un modelo más chico en
Ollama (`ollama pull qwen2.5:3b` y `OLLAMA_MODEL=qwen2.5:3b`).

## 3. Modo evento (con usuarios)

1. `mosquitto\crear_usuarios.bat` → crea `sistema` (publica y lee) y `equipo` (solo lee).
2. En **`config.local.env`** (no se sube a Git; reemplaza a `config.env`): `MQTT_HOST` = IP de la laptop de Bri,
   `MQTT_USER=sistema` y `MQTT_PASS=` su clave, y `MQTT_USER_LECTURA=equipo` y `MQTT_PASS_LECTURA=` su clave (los
   usan los paneles abiertos desde otras laptops). **Nunca pongan claves en `config.env`**, que sí se sube.
3. Firewall, en PowerShell como administrador:
   ```
   Set-NetConnectionProfile -InterfaceAlias "Wi-Fi" -NetworkCategory Private
   New-NetFirewallRule -DisplayName "Apto hoy" -Direction Inbound -Protocol TCP -LocalPort 1883,9001,8080 -Action Allow -Profile Private
   ```
4. Si el servicio de Mosquitto de Windows está activo, detenerlo: `net stop mosquitto` (como administrador).
5. `iniciar.bat` arranca el broker, MongoDB y el registrador, la voz (`--servicio`), el copiloto, el
   coordinador provisional, la visión (`--servicio`) y el servidor de los paneles, cada uno en su ventana.
6. En la laptop de Bri: http://localhost:8080/estacion.html. En el proyector y las otras laptops (misma red):
   http://IP-de-Bri:8080/tripulacion.html y http://IP-de-Bri:8080/tierra.html.

## 4. Temas MQTT

Todo mensaje es JSON y lleva `persona`, `sesion` y `ts`. `control` es un nombre reservado: ninguna persona puede llamarse así.

| Tema | Publica | Lee | Contenido |
|---|---|---|---|
| `apto/control/sesion` | Panel (Sebas), copiloto | Todos | `{"persona", "tarea", "sesion"}`: inicio de una evaluación y persona activa. **Con retain**: el ESP32 (y cualquier módulo que se reinicie) sabe la persona activa al conectarse. La estación lo publica al tocar «Comenzar» (`sesion` = `20261113-193005-bri`). El copiloto lo publica cuando alguien dice «soy Erick», «habla Sebas» o «aquí Bri» (nombres de `TRIPULACION` en `config.env`). |
| `apto/control/modulos/{modulo}` | Todos los módulos de Python (`comun/mqtt_cliente.py`) y el ESP32 | Estación | `{"modulo", "activo": true}` al conectarse, **con retain**; el Last Will publica `{"activo": false}` si el programa se cae, y `cerrar()` lo publica al salir bien. La estación espera los nombres `voz`, `copiloto`, `vision`, `coordinador` y `esp32`. Son cuatro niveles a propósito: `apto/estado/{modulo}` coincidiría con `apto/+/voz`. |
| `apto/control/orden_vision` | Panel (Sebas) | Visión | `{"accion": "medir", "persona", "segundos": 60, "sesion"}`: la estación pide un minuto de medición con la cámara (la estación no abre la cámara: lo hace el módulo de visión, que muestra el rostro en su ventana) |
| `apto/control/estado_vision` | Visión | Panel | `{"persona", "sesion", "estado": "midiendo", "segundos_restantes"}` cada 5 s mientras mide; al terminar `"listo"`, o `"error"` con `"motivo"` (por ejemplo «No se encontró la cámara»). La estación lo muestra en el paso de la cámara. |
| `apto/control/orden_voz` | Panel (Sebas) | Voz | `{"accion": "grabar", "persona", "segundos", "linea_base", "sesion", "frase"}`. `frase`: `estandar` (por defecto), `variacion_1`, `variacion_2` o `trabalenguas`; cada frase tiene su propia línea base |
| `apto/control/escuchar` | Panel (Sebas) | Copiloto | `{"persona", "sesion", "segundos_max"}`: botón 🎤 Hablar de la estación; el copiloto graba con el micrófono de la laptop hasta que la persona se calla, transcribe con Whisper y responde |
| `apto/control/estado_escucha` | Copiloto | Panel | `{"persona", "estado"}`: `escuchando`, `transcribiendo`, `listo` (con `texto`: la pregunta entendida) o `error` (con `motivo`) |
| `apto/control/estado_voz` | Voz | Panel | `{"persona", "estado": "grabando" o "listo"}` |
| `apto/control/pregunta` | Panel (Sebas) | Copiloto | `{"persona", "pregunta", "sesion"}`: pregunta escrita desde la estación |
| `apto/{persona}/esp32` | ESP32 (Adrian) | Coordinador, estación | Cada 1 s: `persona`, `sesion`, `pulso_lpm`, `hrv_rmssd_ms` (RMSSD de 30 s), `spo2`, `dedo`, `movimiento` (g), `calidad` (0 a 1); sin dedo, pulso, HRV y SpO2 en `null`; `"simulado": true` con `MODO_SIMULADO`. El coordinador usa la mediana de las lecturas con dedo y calidad ≥ 0,5: su pulso manda sobre el de la cámara, y la HRV se compara con la línea base. Ver `firmware/README.md` |
| `apto/{persona}/vision` | Visión (Erick) | Coordinador | `perclos` (fracción de 0 a 1 con los ojos cerrados; acepta también porcentaje), `parpadeos_min`, `bostezos` y `bostezos_min`, `pulso_rppg_lpm` (null si la calidad es baja) y `calidad_rppg` (0 a 1), `ear_abierto`, `cabeza_inclinada_pct`, `cara_detectada_pct`, `fps`, `duracion_s`, `avisos`, `linea_base` y la `sesion` de la orden. El coordinador provisional usa el pulso solo si `calidad_rppg` ≥ 0,5, y los parpadeos solo contra la línea base. El módulo usa `ClienteMQTT("vision")` para que la estación lo vea activo. |
| `apto/{persona}/voz` | Voz (Bri) | Coordinador | Tono, jitter, shimmer, HNR, pausas. Con 3 o más mediciones de línea base, también `z_rasgos`, `indice_cansancio` (positivo = más cansancio), `estado_voz` y `motivos_voz` (frases neutras). Es una sugerencia, no un diagnóstico. |
| `apto/{persona}/pvt` | PVT (Sebas) | Coordinador | PVT-B en el navegador: `rt_media_ms`, `rt_mediana_ms`, `lapsos` (355 ms o más, o sin respuesta en 30 s), `anticipadas` (antes del estímulo o en menos de 100 ms), `lapsos_por_min` y `anticipadas_por_min` (para comparar 3 min con 1 min), `n_estimulos`, `duracion_s`, `linea_base`, `modo_demo` (true = 1 minuto) |
| `apto/{persona}/dsst` | Panel (Sebas) | Coordinador | Prueba de símbolos (DSST, 90 s, opcional): `correctas`, `incorrectas`, `por_minuto` (correctas por minuto), `duracion_s`, `linea_base` || `apto/{persona}/cuestionario` | Panel (Sebas) | Coordinador | `kss` (escala de somnolencia de Karolinska, 1 a 9), `kss_texto`, `horas_sueno` (de 0 a 16, de media en media hora), `linea_base` |
| `apto/{persona}/evaluacion` | Coordinador (Danilo; por ahora el provisional) | Paneles, copiloto | `color`, `puntaje`, `motivos`, `accion`, `pesos` y `sesion` (la de la estación, para que la estación lo reconozca). El provisional agrega `"provisional": true`, `senales` (puntos por fuente) y `aviso_spo2` (true si el SpO2 del ESP32 estuvo bajo 30 s seguidos: **no cambia el color**; va con el motivo «Oxígeno más bajo de lo habitual: repetir la medición»). **Publicar con retain.** Los `motivos` se escriben como frases neutras, sin sujeto («Menos horas de sueño de lo habitual», no «Durmió menos»), porque el copiloto los lee después de «tu resultado… Motivos:». |
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
- **Examen de voz con variaciones (opcional)**: en el paso de voz se elige la frase: la estándar (por defecto) o
  variaciones de menos a más difícil hasta un trabalenguas. Cada frase tiene su **propia línea base** (una
  medición solo se compara con las de la misma frase), así que cada una necesita sus 3 mediciones de línea base.
- **Preguntar por voz**: en el resultado, el botón 🎤 Hablar le pide al copiloto que escuche con el micrófono de la
  laptop; se detiene solo cuando la persona se calla (o a los 10 s), transcribe con Whisper y responde en voz alta
  y en pantalla. Necesita el copiloto abierto en modo voz (`iniciar.bat`; con `--texto` no tiene Whisper).
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
**SpO2: aviso, no puntaje.** Si durante al menos 30 s seguidos, con dedo y calidad ≥ 0,5, el SpO2 está 4 puntos o
más por debajo del promedio de la línea base de la persona (o por debajo de 92 si no tiene línea base), la evaluación
lleva `"aviso_spo2": true` y el motivo «Oxígeno más bajo de lo habitual: repetir la medición», **sin cambiar el
color**. Sacar el dedo o una lectura normal cortan la racha. La estación lo muestra en amarillo debajo del semáforo y
el copiloto lo dice al final del resumen. Para probarlo: `python herramientas\simulador.py --persona bri --esp32 40
--spo2 89` durante una sesión, antes del cuestionario.
**Pulso: manda el sensor.** Si llegan lecturas del ESP32 en la sesión (una por segundo; se usa su mediana), su
pulso es el que cuenta y el de la cámara (rPPG) no se usa; sin sensor, el de la cámara solo cuenta si
`calidad_rppg` ≥ 0,5.

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
  `datos\mongo` y la caché limitada a 256 MB (`--wiredTigerCacheSizeGB 0.25`; usa unos 160 MB). Si el puerto
  de `MONGO_URI` ya está ocupado, no arranca otro y avisa. `config.env`:
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

## 8. Visión (pulso sin contacto, parpadeos y PERCLOS)

`vision\vision.py` (MediaPipe 1.2, API Tasks `FaceLandmarker`; el modelo `face_landmarker.task` va en `modelos\`).
Cámara en `config.env`: `CAMARA=0` (índice; `--listar` muestra las disponibles) o la URL de DroidCam
(`http://IP:4747/video`). Duración: `VISION_SEGUNDOS=60`.

**Con el celular (DroidCam)**: abrir la app en el celular, conectado al mismo Wi-Fi que la laptop; la app muestra
«WiFi IP» y el puerto 4747. Poner `CAMARA=http://ESA_IP:4747/video` y reiniciar el servicio de visión. No hace falta
el programa DroidCam de Windows (si se usa, su cámara virtual aparece en `--listar` solo cuando está conectado).
La cámara del celular suele dar más cuadros por segundo y mejor imagen que la de la laptop, y eso mejora el pulso.
Solo un programa a la vez puede recibir la imagen de DroidCam.

| Modo | Qué hace |
|---|---|
| `--listar` | Lista las cámaras |
| `--ver` | Vista previa en vivo (sin medir ni publicar): malla del rostro, regiones del pulso (frente y mejillas), pulso estimado y EAR. `q` o `Esc` para salir |
| `--persona bri` | Una medición con ventana; `--linea-base`, `--sin-ventana`, `--sin-mqtt`, `--referencia 72` |
| `--referencia 72` (solo) | Guarda el pulso medido con otro aparato junto al último estimado, en `datos\vision\validacion.csv` |
| `--servicio` | Espera `apto/control/orden_vision`. Al recibir la orden **abre sola la ventana** mientras mide (la estación le dice a la persona que ahí ve su rostro), publica `estado_vision` (`midiendo` con los segundos que faltan cada 5 s, y `listo` o `error` con el motivo), cierra la ventana y suelta la cámara. Se anuncia como `ClienteMQTT("vision")` |

Publica `apto/{persona}/vision` (ver la tabla de la sección 4) y guarda cada medición en
`datos\vision\historial.jsonl` (con el pulso aunque sea dudoso, para validar).

- **Pulso (rPPG)**: promedio RGB de la frente y las mejillas en cada cuadro, con su hora; se vuelve a muestrear
  a 30 Hz; método POS (ventanas de 1,6 s); filtro de banda en el espectro de 0,7 a 3 Hz (42 a 180 lpm); el
  pico da el pulso. **Calidad** = relación señal/ruido del pico (potencia a ±0,1 Hz del pico y de su armónico
  contra el resto de la banda) llevada a 0..1: `(SNR dB + 3) / 12`. Si es menor que 0,5, **no se publica el
  número**: va un aviso.
- **Ojos**: EAR con 6 puntos por ojo (promedio de los dos). EAR de ojo abierto = mediana de los primeros 5 s.
  Parpadeo = EAR por debajo del 60 % de ese valor durante al menos 2 cuadros. **PERCLOS** = fracción del tiempo
  (con la cara visible) con EAR por debajo del 30 % del valor abierto. Es una aproximación del criterio «ojo
  cerrado al 80 %» (P80): el EAR no llega a 0 con el ojo cerrado, por cómo caen los puntos de la malla; no
  está validado clínicamente. **Mirar hacia abajo** baja el párpado y parece un ojo cerrado: los cuadros con la
  cabeza inclinada más de 15 grados respecto de los primeros 5 s (inclinación que da MediaPipe) no cuentan para
  los ojos, y se informa `cabeza_inclinada_pct`. Cerrar los ojos no mueve la cabeza, así que un cierre real cuenta.
  Por eso, durante la medición conviene mirar la ventana de frente.
- **Bostezos**: MAR (apertura de la boca) = promedio de 3 aperturas internas de los labios / ancho entre las
  comisuras internas. Bostezo = MAR ≥ 0,6 que se mantiene (hasta bajar de 0,45) al menos 1,5 s; hablar abre la
  boca menos y por menos tiempo. Mientras dura un bostezo los ojos se achican: esos cuadros no cuentan para los
  parpadeos ni el PERCLOS. La ventana muestra el contador y avisa cuando la boca está muy abierta.
- **Avisos de calidad**: poca luz (brillo de la piel < 60 de 255), demasiada luz o reflejos (> 210, o más del
  5 % de la piel saturada), cara no detectada más del 20 % del tiempo, menos de 15 cuadros por segundo y pulso
  poco confiable. La ventana muestra los de luz en vivo.
- **Validación**: medir con la cámara y, al mismo tiempo, con otro aparato (oxímetro o reloj); luego
  `python vision\vision.py --referencia <lpm>`. `validacion.csv` guarda el estimado, la referencia, el error,
  la calidad, los fps y la cara detectada, para calcular el error medio después.
- **Prueba**: `python vision\pruebas_vision.py` (señales sintéticas: pulso de 72 lpm → 72 ± 3, parpadeos
  conocidos, PERCLOS, avisos y ventana).

## 9. Reglas para sumar un módulo (todo el equipo)

1. Cada módulo vive en su carpeta, con `requirements.txt` y un README con el comando para correrlo.
2. Usen `comun/mqtt_cliente.py`; nunca escriban la IP ni claves en el código (las opciones van en `config.env`; las
   claves y los valores de cada laptop, en `config.local.env`, que no se sube a Git). Así el
   módulo avisa solo si está abierto (`ClienteMQTT("vision")` → `apto/control/modulos/vision`).
3. En casa: Mosquitto propio con `mosquitto\mosquitto-dev.conf` y `MQTT_HOST=localhost`.
4. Prueben con `herramientas\simulador.py` y `herramientas\escuchar.py` sin esperar a los demás.
5. El ESP32 se conecta con el usuario `sistema` y su clave, a la IP de Bri, puerto 1883.

## Avisos

- Las fichas de `copiloto/protocolos.md` son una guía interna del prototipo: revísenlas y agreguen fuentes antes de presentar.
- Es un prototipo de apoyo a la decisión, no un dispositivo médico, y no diagnostica.
- Este código se desarrolló con ayuda de IA (Claude); el equipo lo revisó y probó.
