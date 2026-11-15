# Prueba de salud 


Repositorio común del equipo: todos los módulos (ver «Equipo»), la conexión MQTT que usan todos, la configuración
de Mosquitto, un simulador y los scripts de Windows.

## Equipo

| Integrante | Módulo |
|---|---|
| **Bri** | Voz (fatiga en la voz) y copiloto por voz; la laptop de la estación (broker e integración) |
| **Danilo** | Coordinador (calcula el semáforo; mientras tanto corre el coordinador provisional) y firmware del ESP32 (3 LED, zumbador, modo local sin Wi-Fi) |
| **Sebas** | Paneles (estación, tripulación y Tierra) y prueba de reacción (PVT) |
| **Erick** | Visión (cámara: parpadeos, PERCLOS y bostezos) |
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
├── paneles/              paneles web: estación Becspace, tripulación y Tierra (servidor.py, sin internet)
├── coordinador/          coordinador_provisional.py, hasta que esté el de Danilo
├── registrador/          guarda todo apto/# en MongoDB, exporta a CSV y reproduce sesiones
├── herramientas/         simulador.py (datos falsos) y escuchar.py (ver mensajes)
├── mosquitto/            configuración del broker (evento y desarrollo)
├── vision/               parpadeos, PERCLOS y bostezos por cámara (MediaPipe)
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
| Visión | `python vision\vision.py --ver` (vista previa) o `--persona bri` (una medición) | Malla del rostro, EAR, parpadeos y bostezos en vivo (sección 8) |
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
| `apto/control/estado_vision` | Visión | Panel | `{"persona", "sesion", "estado": "midiendo", "segundos_restantes"}` cada 5 s mientras mide; antes de empezar, si ve lentes, `"lentes"` con `"mensaje"` (pide quitarlos) y `"espera_s"`; al terminar `"listo"`, o `"error"` con `"motivo"` (por ejemplo «No se encontró la cámara»). La estación lo muestra en el paso de la cámara. |
| `apto/control/orden_voz` | Panel (Sebas) | Voz | `{"accion": "grabar", "persona", "segundos", "linea_base", "sesion", "frase"}`. `frase`: `estandar` (por defecto), `variacion_1`, `variacion_2` o `trabalenguas`; cada frase tiene su propia línea base |
| `apto/control/escuchar` | Panel (Sebas) | Copiloto | `{"persona", "sesion", "segundos_max"}`: botón 🎤 Hablar de la estación; el copiloto graba con el micrófono de la laptop hasta que la persona se calla, transcribe con Whisper y responde |
| `apto/control/estado_escucha` | Copiloto | Panel | `{"persona", "estado"}`: `escuchando`, `transcribiendo`, `listo` (con `texto`: la pregunta entendida) o `error` (con `motivo`) |
| `apto/control/estado_voz` | Voz | Panel | `{"persona", "estado": "grabando" o "listo"}` |
| `apto/control/pregunta` | Panel (Sebas) | Copiloto | `{"persona", "pregunta", "sesion"}`: pregunta escrita desde la estación |
| `apto/{persona}/esp32` | ESP32 (Adrian) | Coordinador, estación | Cada 1 s: `persona`, `sesion`, `pulso_lpm`, `hrv_rmssd_ms` (RMSSD de 30 s), `spo2`, `dedo`, `movimiento` (g), `calidad` (0 a 1); sin dedo, pulso, HRV y SpO2 en `null`; `"simulado": true` con `MODO_SIMULADO`. El coordinador usa la mediana de las lecturas con dedo y calidad ≥ 0,5: su pulso manda sobre el de la cámara, y la HRV se compara con la línea base. Ver `firmware/README.md` |
| `apto/{persona}/vision` | Visión (Erick) | Coordinador | `perclos` (fracción de 0 a 1 con los ojos cerrados; acepta también porcentaje), `parpadeos_min`, `bostezos` y `bostezos_min` (incluyen los tapados con la mano), `bostezos_tapados`, `lentes` (true si se midió con lentes puestos: los ojos no cuentan), `ear_abierto`, `cabeza_inclinada_pct`, `cara_detectada_pct`, `fps`, `duracion_s`, `avisos`, `linea_base` y la `sesion` de la orden. El coordinador provisional usa los parpadeos solo contra la línea base. El pulso por cámara (rPPG) se quitó: el pulso es solo el del ESP32. El módulo usa `ClienteMQTT("vision")` para que la estación lo vea activo. |
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
(mqtt.js 5.16.1), los íconos (Phosphor) y la fuente (Inter) están en `paneles/web/vendor/`; no hay CDN.

La estación usa el diseño **Becspace** (hecho en Claude Design, sistema de diseño Nocturne en `paneles/web/nocturne.css`):
barra lateral con el logo animado, fondo con la Tierra de noche (o claro) y siete pantallas:

| Pantalla | Qué muestra (todo con datos reales de MQTT) |
|---|---|
| Panel | Recomendación para la tarea (la misma de `resumen_tripulacion()` del copiloto), conteo por color, una tarjeta por integrante (pulso, KSS y PVT), módulos abiertos, aviso de SpO2 y últimas respuestas del copiloto |
| Evaluación | Paso a paso: inicio (persona, tarea, línea base, modo demo, símbolos y verificación de broker y módulos), dispositivo (pulso, HRV, SpO₂ y movimiento del ESP32), voz (frase de `voz_fatiga.py`), reacción PVT-B (1 min; **la cámara mide al mismo tiempo**, sin abrir su ventana), símbolos DSST (90 s, opcional), cuestionario de Karolinska y la espera del coordinador |
| Pruebas | Cámara y micrófono de este navegador (imagen, luz, nivel, ruido y una grabación de 3 s), sin guardar nada |
| Resultados | Semáforo, motivos, recomendación, aviso de SpO2, Becspace AI (el copiloto: pregunta escrita o 🎤 Hablar) e indicadores por fuente: medido, estimado, reportado o no disponible, con su calidad y sus puntos |
| Historial | Evaluaciones guardadas por el registrador (MongoDB): gráfico por indicador, tabla, detalle, exportar CSV y el comando para reproducir la sesión |
| Configuración | Ícono de cada tripulante, tema oscuro o claro, texto grande para proyector, reducir movimiento, alto contraste, permisos y los valores de `config.env` (se cambian en `config.local.env`) |
| Sistema de diseño | Logo, colores, tipografía, botones y estados de la interfaz |

| Página | Para qué | Quién la usa |
|---|---|---|
| http://localhost:8080/estacion.html | La estación completa (empieza en el Panel; «Nueva evaluación» abre la evaluación) | La persona que se evalúa, en la laptop de Bri (al tocar «Comenzar» pasa a pantalla completa) |
| http://IP-de-Bri:8080/tripulacion.html | La misma estación en solo lectura: Panel, resultados e historial; no puede publicar | Proyector y otras laptops |
| http://IP-de-Bri:8080/tierra.html | Las evaluaciones llegan con `RETRASO_TIERRA_S` de retraso: se ve que la tripulación decidió antes de que Tierra se enterara | Control de misión (solo lectura) |

- **Credenciales**: si la página se abre en la misma laptop (localhost), `/config.js` lleva `MQTT_USER` y
  `MQTT_PASS` (puede publicar). Desde otra laptop lleva `MQTT_USER_LECTURA` y `MQTT_PASS_LECTURA` (solo lee).
  Por eso la estación solo funciona en la laptop de Bri. En desarrollo todos quedan vacíos.
- **Opciones** en `config.env`: `PVT_SEGUNDOS` (60, lo mismo que mide la cámara; 180 = PVT-B de 3 minutos; la casilla «Modo demo» de la estación
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
  El ESP32 no es un módulo de Python: si en 10 s no llegan datos, la estación lo avisa (y recuerda que los tres
  LED encendidos significan que no llega al broker).
- **Cámara junto con la reacción**: la cámara ya no tiene paso propio. Al tocar «Empezar la prueba», la estación
  pide la medición (`orden_vision` con `"ventana": false` y los mismos segundos que la prueba) y arranca cuando el
  módulo empieza a medir; así nadie pasa un minuto quieto mirando la cámara. Si el módulo ve lentes
  (`estado_vision` `"lentes"`), el pedido de quitárselos sale en el área de la prueba antes de empezar. Al terminar
  dice si llegaron los datos de la cámara. Los parpadeos medidos durante una tarea no son comparables con líneas
  base tomadas mirando la cámara sin hacer nada.
- **Cancelar evaluación**: botón en todos los pasos; corta la evaluación sin publicar resultado y avisa al ESP32
  (`apto/control/cancelar`).
- **Sin caché**: `servidor.py` responde todo con `Cache-Control: no-store`, para que la estación cargue siempre la
  versión nueva después de actualizar el proyecto.
- Cada página muestra si está conectada al broker. Los datos con `"simulado": true` llevan la etiqueta SIMULADO, y
  los del coordinador provisional, PROVISIONAL. La onda del pulso en el paso del dispositivo es ILUSTRATIVA: va al
  ritmo del pulso medido, porque el ESP32 manda un resumen por segundo y no la señal cruda.
- **Historial**: `servidor.py` lee el MongoDB del registrador (`/historial.json`, `/historial.csv` y `/sesion.json`,
  ver `paneles/historial.py`; solo lee). Necesita `pymongo` en el Python de `servidor.py` (`instalar.bat` ya lo
  instala para el registrador) y MongoDB abierto; si no, la pantalla lo dice y el resto funciona igual. Con el
  historial, el Panel y los Resultados se completan aunque la página se abra después de la evaluación.
- **Atajos para probar** una pantalla sin hacer todo el recorrido: `estacion.html?pantalla=historial` (dashboard,
  evaluacion, pruebas, resultados, historial, config, sistema) y `estacion.html?paso=reaccion&persona=bri&demo=1`
  (pasos: dispositivo, camara, voz, reaccion, simbolos, cuestionario, resultado; `&dsst=1` agrega los símbolos).
  `?paso=` no publica la sesión.
- **Prueba**: `python paneles\pruebas_paneles.py` (servidor, `/config.js`, historial sin MongoDB, que no se salga de
  `paneles/web`, sin recursos externos, `node --check`, el escape de las plantillas y la recomendación comparada con
  la del copiloto).

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
**SpO2: aviso, no puntaje.** Si durante al menos 20 s seguidos (de los 30 s que mide el ESP32), con dedo y calidad ≥ 0,5, el SpO2 está 4 puntos o
más por debajo del promedio de la línea base de la persona (o por debajo de 92 si no tiene línea base), la evaluación
lleva `"aviso_spo2": true` y el motivo «Oxígeno más bajo de lo habitual: repetir la medición», **sin cambiar el
color**. Sacar el dedo o una lectura normal cortan la racha. La estación lo muestra en amarillo debajo del semáforo y
el copiloto lo dice al final del resumen. Para probarlo: `python herramientas\simulador.py --persona bri --esp32 40
--spo2 89` durante una sesión, antes del cuestionario.
**Pulso: solo el del sensor.** Se usa la mediana de las lecturas del ESP32 de la sesión (una por segundo). El pulso
por cámara (rPPG) se quitó porque con la luz de la estación no llegaba a la calidad mínima; si un mensaje viejo trae
`pulso_rppg_lpm`, no se usa. En la pantalla de resultados, «Fatiga por visión» resume la cámara: vale lo que su
peor indicador (ojos cerrados, parpadeos o bostezos): sin signos, leve o marcada.

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

## 8. Visión (parpadeos, PERCLOS y bostezos)

`vision\vision.py` (MediaPipe 1.2, API Tasks `FaceLandmarker` y `HandLandmarker`; los modelos `face_landmarker.task`
y `hand_landmarker.task` van en `modelos\`: los baja `instalar.bat`, o el módulo la primera vez).
Cámara en `config.env`: `CAMARA=0` (índice; `--listar` muestra las disponibles) o la URL de DroidCam
(`http://IP:4747/video`). Duración: `VISION_SEGUNDOS=60`.

**Con el celular (DroidCam)**: abrir la app en el celular, conectado al mismo Wi-Fi que la laptop; la app muestra
«WiFi IP» y el puerto 4747. Poner `CAMARA=http://ESA_IP:4747/video` y reiniciar el servicio de visión. No hace falta
el programa DroidCam de Windows (si se usa, su cámara virtual aparece en `--listar` solo cuando está conectado).
La cámara del celular suele dar más cuadros por segundo y mejor imagen que la de la laptop, y eso mejora la malla del rostro.
Solo un programa a la vez puede recibir la imagen de DroidCam.

**DroidCam por cable USB** (Android; no depende del Wi-Fi): activar en el celular las opciones de desarrollador
(tocar 7 veces «Número de compilación») y la «Depuración USB», conectar con un cable de datos, aceptar el permiso y
dejar la app DroidCam abierta en pantalla. En `config.local.env`: `CAMARA=http://127.0.0.1:4747/video`. Antes de
cada medición la visión ejecuta `adb forward tcp:4747 tcp:4747` (se pierde al desconectar el celular). Usa el `adb`
de Android SDK Platform-Tools; si está en otro lugar, poner su ruta en `ADB=`.

| Modo | Qué hace |
|---|---|
| `--listar` | Lista las cámaras |
| `--ver` | Vista previa en vivo (sin medir ni publicar): malla del rostro, zonas donde se mide la luz (frente y mejillas), EAR, parpadeos y bostezos. `q` o `Esc` para salir |
| `--persona bri` | Una medición con ventana; `--linea-base`, `--sin-ventana`, `--sin-mqtt`, `--diagnostico` |
| `--servicio` | Espera `apto/control/orden_vision`. Al recibir la orden **abre sola la ventana** mientras mide (la estación le dice a la persona que ahí ve su rostro), publica `estado_vision` (`midiendo` con los segundos que faltan cada 5 s, y `listo` o `error` con el motivo), cierra la ventana y suelta la cámara. Se anuncia como `ClienteMQTT("vision")` |

Publica `apto/{persona}/vision` (ver la tabla de la sección 4) y guarda cada medición en
`datos\vision\historial.jsonl`.

- **Ojos**: EAR con 6 puntos por ojo. Para los parpadeos y el PERCLOS cuenta el ojo **más abierto** de los dos: un
  parpadeo o un cierre son con los dos ojos, y cerrar uno solo (un guiño) no cuenta. Para los bostezos se usa el
  promedio de los dos. EAR de ojo abierto = mediana de los primeros 5 s.
  Parpadeo = EAR por debajo del 60 % de ese valor durante al menos 2 cuadros. **PERCLOS** = fracción del tiempo
  (con la cara visible) con EAR por debajo del 30 % del valor abierto. Es una aproximación del criterio «ojo
  cerrado al 80 %» (P80): el EAR no llega a 0 con el ojo cerrado, por cómo caen los puntos de la malla; no
  está validado clínicamente. **Mirar hacia abajo** baja el párpado y parece un ojo cerrado: los cuadros con la
  cabeza inclinada más de 15 grados respecto de los primeros 5 s (inclinación que da MediaPipe) no cuentan para
  los ojos, y se informa `cabeza_inclinada_pct`. Cerrar los ojos no mueve la cabeza, así que un cierre real cuenta.
  Por eso, durante la medición conviene mirar la ventana de frente.
- **Bostezos**: MAR (apertura de la boca) = promedio de 3 aperturas internas de los labios / ancho entre las
  comisuras internas. Bostezo = MAR ≥ 0,6 que se mantiene (hasta bajar de 0,45) al menos 1,5 s; hablar abre la
  boca menos y por menos tiempo. Además tiene que mostrar **al menos una señal de bostezo**: los ojos se
  entrecierran (EAR suavizado < 85 % del abierto al menos 0,5 s seguidos), la boca sigue abierta 2,5 s o más, o se
  abrió de a poco (de MAR 0,3 a 0,6 en 0,4 s o más). En las trazas reales, los bostezos simulados quedaron
  abiertos de 2,3 a 4,8 s, se abrieron en 0,43 a 3,2 s y achicaron los ojos 1,4 s o más. Los gestos de boca muy
  abierta al hablar se abrieron de golpe (0,14 a 0,29 s), duraron de 0,5 a 1,6 s y casi nunca achicaron los ojos.
  Uno de ellos (MAR 0,93 durante 1,56 s, ojos al 99-118 %) contaba antes como bostezo. La mandíbula no sirve para
  distinguirlos: sube igual (+25 %) en los dos. Las tres señales se calculan con lo que pasó hasta cada cuadro y solo
  pueden pasar de «no» a «sí», así que el contador en vivo no baja. **Límite conocido**: un gesto que mantenga la
  boca muy abierta 2,5 s o más todavía cuenta. Mientras dura un bostezo los ojos se achican: esos cuadros no
  cuentan para los parpadeos ni el PERCLOS. La ventana muestra el contador y avisa cuando la boca está muy abierta.
  Cada bostezo con la boca a la vista se explica en la consola (momento, duración, MAR al empezar, máximo, mediana y
  al terminar, tiempo de apertura, ojos, mandíbula, si después llegó la mano y qué señales lo hicieron bostezo).
  Con `--diagnostico` (o `VISION_DIAGNOSTICO=1`) también salen las aperturas descartadas y el motivo. Se ajustan en
  `config.local.env`: `BOSTEZO_VISTO_OJOS_S` (0,5), `BOSTEZO_LARGO_S` (2,5) y `BOSTEZO_SUBIDA_S` (0,4).
- **Bostezos tapados con la mano** (en Bolivia, como en otros lugares, se bosteza tapándose la boca, y entonces
  el MAR no sirve): MediaPipe Hands (`hand_landmarker.task`, 1 de cada 2 cuadros, a media resolución) marca
  «mano en la boca» cuando 4 o más de los 21 puntos de una mano caen en el rectángulo de la boca y la nariz.
  Con la mano encima, el MAR de esos cuadros no cuenta. La decisión es temporal: por cada vez que la mano queda
  ahí al menos 1 s se mira
  1. si la boca se abrió en los 1,5 s anteriores a la mano o entre los dedos (MAR ≥ 0,5 al menos 0,3 s, o ≥ 0,3
     al menos 0,6 s seguidos: se abre de a poco; al hablar abre y cierra varias veces por segundo);
  2. si la mano tapó antes de poder ver la boca: si la mandíbula bajó con la mano encima. Es el largo de la cara
     **en 3D** (con la profundidad de la malla), de la raíz de la nariz al mentón, suavizado en ~0,5 s, que crece
     un 8 % o más sobre el de reposo durante al menos 0,8 s. En 3D, girar o inclinar la cabeza no lo cambia; en la
     imagen plana, girarla 30° lo subía un 15 %. O bien, si los ojos quedaron **muy cerrados** (< 60 % del abierto)
     al menos 1,5 s con la mano ahí: con la mano encima la malla inventa la boca y la mandíbula, y lo que se ve es
     que los pómulos suben y cierran los ojos. En las pruebas reales con 5 personas, una mano en la boca sin
     bostezar dejó los ojos al 87 % o más;
  3. siempre, si los ojos se entrecerraron: el EAR, suavizado con la mediana de 5 cuadros, queda por debajo del
     85 % del abierto al menos 0,3 s seguidos, entre 1,5 s antes de la mano y 0,5 s después de que se va. Es
     suave a propósito: hay quien casi no achica los ojos al bostezar.

  Es bostezo con 3 y además 1 o 2. Con eso no cuentan la tos tapada (la boca se abre muy poco tiempo), la mano
  quieta en la boca ni la mano en el mentón al hablar (la mandíbula sube y baja rápido). Un bostezo que se ve y
  después se tapa cuenta una vez. **Estabilidad**: el ojo abierto y la mandíbula de reposo de cada mano salen de
  los 20 s anteriores a esa mano (sigue a la persona que está delante, también si cambia en `--ver`), y todas las
  condiciones solo pueden pasar de «no» a «sí». Así una decisión tomada no cambia y el contador en vivo nunca
  baja; antes se recalculaba todo con el promedio de la sesión y bajaba al moverse o al cambiar de persona.
  Se publica `bostezos` (todos) y `bostezos_tapados`. Con la mano en la cara,
  esos cuadros no cuentan para medir la luz. Si no se puede usar la detección de manos, se mide igual y va un aviso.
  **Diagnóstico**: cada vez que la mano se va de la boca, la consola explica qué se midió y qué faltó (por
  ejemplo «ojos hasta el 88 % del abierto… los ojos casi no se entrecerraron»); en `--ver` también sale en la
  ventana, y al cerrar se guardan las series (sin imágenes) en `datos\vision\trazas\ver-*.npz`. Los umbrales se
  ajustan en `config.local.env`: `BOSTEZO_OJOS_FRAC` (0,85), `BOSTEZO_OJOS_S` (0,3), `BOSTEZO_MANDIBULA` (0,08) y
  `BOSTEZO_OJOS_MUY_FRAC` (0,60).
- **Lentes**: MediaPipe no trae un clasificador de lentes, y no usamos uno aparte. Un YOLO o una red de
  lentes necesitaría un modelo entrenado por terceros y PyTorch, y en esta laptop no hay memoria para eso.
  Las cascadas Haar de OpenCV encuentran ojos, con o sin lentes, pero no dicen si hay lentes. Así que, con la
  malla, se ubica el puente de la nariz entre los ojos (puntos 168 y 6), por donde cruza la montura. Se
  endereza la imagen con la línea de los ojos y se mide ahí el borde horizontal más marcado (Sobel vertical).
  Se divide por la textura típica de la piel (mediana de mejillas y frente): sin lentes, el puente es piel lisa
  (puntaje cerca de 1 a 3); con montura sube mucho. Se decide con 2 s de cuadros: hay lentes si el 60 % o más
  pasa `LENTES_UMBRAL`. Antes de medir, si hay lentes, la ventana muestra «SE VEN LENTES: quítatelos» y se
  publica `estado_vision` `"lentes"` con el `mensaje`; la estación lo muestra en amarillo. La medición empieza
  sola cuando ya no se ven. Si a los `LENTES_ESPERA_S` (30 s) siguen puestos, se mide igual con
  `"lentes": true` y un aviso, y el coordinador no usa los ojos. Lentes sin montura o de montura muy fina pueden
  no detectarse. **Ajuste**: con `--ver` la ventana muestra el puntaje (arriba a la derecha); mirarlo con y sin
  lentes y poner `LENTES_UMBRAL` entre los dos en `config.local.env`. `LENTES_REVISAR=0` lo apaga.
- **Avisos de calidad**: poca luz (brillo de la piel < 60 de 255), demasiada luz o reflejos (> 210, o más del
  5 % de la piel saturada), cara no detectada más del 20 % del tiempo, y menos de 15 cuadros por segundo.
  La ventana muestra los de luz en vivo.
- **Prueba**: `python vision\pruebas_vision.py` (señales sintéticas: parpadeos
  conocidos, PERCLOS, bostezos tapados, falsos positivos de bostezo al hablar o gesticular, lentes, avisos y
  ventana).

## 9. ESP32: luces y respaldo sin Wi-Fi

Firmware en `firmware\apto_esp32\`. El cableado, las librerías y cómo subirlo están en `firmware/README.md`. El
ESP32 muestra el semáforo en un **LED RGB**, en la pantalla OLED y con el zumbador:
- **LED RGB:** rojo en GPIO 25, verde en GPIO 26 y azul en GPIO 27, cada canal con 220 Ω (cátodo común a GND; con
  ánodo común, `LED_ANODO_COMUN 1`). **Nunca se encienden los tres canales a la vez**, para no forzarlo.
- **Zumbador:** suena con un tono de 2 kHz, así que sirve uno activo o uno pasivo; da 3 pitidos al pasar a rojo.

| LED | Significa |
|---|---|
| Verde, amarillo (rojo + verde) o rojo | El resultado **final** de la evaluación en curso (`apto/{persona}/semaforo` de esa sesión) |
| **Azul fijo** | Evaluación en curso (midiendo o esperando el resultado), o **sin conexión al broker** |
| Azul parpadeando | Modo local: «repite» (hubo poca señal buena) |
| Apagado | En reposo, o evaluación cancelada |
| Al arrancar: rojo, verde y azul, de a uno, y un pitido | Prueba del cableado |

**Con Wi-Fi, la placa sigue la evaluación de la estación** y la OLED anuncia cada paso:

1. «INICIAR ANALISIS» (un pitido) cuando la estación publica una sesión nueva (`apto/control/sesion`), y después el
   nombre de quien se evalúa.
2. «Coloca tu dedo», cuenta 3-2-1 y **30 s de medición** con cuenta regresiva. Si se retira el dedo, «Dedo retirado:
   repite»; si hubo menos de 10 s de señal buena, «Senal debil: repite».
3. «MEDIDO» con el pulso, el SpO₂ y la HRV de esos 30 s: ya se puede retirar el dedo. La placa **solo publica
   lecturas durante los 30 s**; fuera de ellos `pulso_lpm`, `hrv_rmssd_ms` y `spo2` van en `null`.
4. El color y «Resultado final» **recién cuando el coordinador publica el semáforo de esa sesión**, con todas las
   pruebas. Un semáforo de una sesión anterior se ignora. Queda hasta la próxima evaluación.

Cada mensaje `apto/{persona}/esp32` lleva `fase` (`reposo`, `anuncio`, `nombre`, `espera`, `cuenta`, `midiendo`,
`listo`, `resultado`, `cancelada`), `quedan_s` mientras mide y, al terminar, `medicion_lista: true` con
`pulso_medido_lpm`, `hrv_medido_ms` y `spo2_medido`. La estación habilita «Continuar» con `medicion_lista`.

**Cancelación**: «CANCELADA» y el motivo, LED apagado y vuelta a «Listo» si la estación publica
`apto/control/cancelar` (`{"persona", "sesion", "motivo"}`, retenido; botón «Cancelar evaluación»), si la placa pasa
20 s sin broker durante una evaluación («Sin conexion») o si pasan 15 min sin resultado final («Sin resultado»).

### Respaldo de la demo: medición sin Wi-Fi (modo local)

Si en la demo fallan la red o la laptop, el ESP32 puede medir solo, sin Wi-Fi ni MQTT:

1. En `firmware\apto_esp32\secrets.h` dejar `#define WIFI_SSID ""` (vacío) y volver a subir el firmware. Conviene
   hacerlo **antes** de la demo y tener las dos versiones a mano, porque cambiar de modo exige volver a subir el
   firmware.
2. La OLED dice «Coloca tu dedo». Al poner el dedo cuenta 3-2-1, con un pitido corto en cada número.
3. Mide 30 s (la ventana de la HRV) con cuenta regresiva y el pulso en vivo, con **los tres LED encendidos**. Si se
   retira el dedo, dice «Dedo retirado: repite».
4. Muestra el resultado con las mismas reglas que el coordinador sin línea base:

   | Resultado | Cuándo | LED | Zumbador |
   |---|---|---|---|
   | VERDE | Pulso de 50 a 99 | Verde | 1 pitido corto |
   | AMARILLO | Pulso de 100 a 119 («Pulso en reposo alto») o de 40 a 49 («Pulso bajo») | Amarillo | 1 pitido |
   | ROJO | Pulso de 120 o más, o menor que 40 («Pulso muy bajo») | Rojo | 3 pitidos |
   | REPITE | Menos de 10 s de señal buena | Los tres parpadeando | 2 pitidos largos |

   - **SpO₂:** si es menor que 92, solo agrega «Oxigeno bajo» en la OLED, sin cambiar el color (la misma
     regla que el aviso de SpO₂ del coordinador).
   - **HRV:** se muestra, pero no se juzga, porque no hay línea base.
5. Para otra medición, retirar el dedo y volver a ponerlo.

**Es un respaldo, no la evaluación completa:** solo usa el pulso del sensor. No hay cámara, voz, prueba de reacción,
cuestionario ni línea base, y nada llega a los paneles ni a MongoDB. La OLED muestra el nombre de
`PERSONA_INICIAL` (en `config.h`), porque sin red no recibe la persona de la estación. Para volver al modo normal,
poner otra vez el Wi-Fi en `secrets.h` y subir el firmware.

Para probar los colores sin sensor hay que compilar en modo simulado con un pulso fijo; con 130 sale ROJO:
```
arduino-cli compile --fqbn esp32:esp32:esp32 --build-property "compiler.cpp.extra_flags=-DMODO_SIMULADO=1 -DPULSO_FORZADO=130" firmware\apto_esp32
```

## 10. Reglas para sumar un módulo (todo el equipo)

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
