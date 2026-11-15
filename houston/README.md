# Houston (control de misión en Tierra)

Todo lo demás del repositorio vive **en la nave**: broker Mosquitto, módulos, registrador con MongoDB y paneles.
Houston es lo que está **en Tierra**: se suscribe a Mosquitto, guarda en **su propio MongoDB** lo que baja de la nave
(con el retraso de la comunicación) y lo muestra en **su propio servidor web**. Solo lee: no publica nada por MQTT y
la estación no lo ve como un módulo.

```
nave (laptop de Bri)                         Tierra (Docker)
módulos --MQTT--> Mosquitto :1883  ------->  receptor.py --> MongoDB houston --> servidor.py :8090 --> navegador
```

## Arrancar con Docker

Necesita Docker Desktop abierto. Desde la carpeta `houston`:

```
docker compose up -d --build        levanta mongo, receptor y web  ->  http://localhost:8090
docker compose logs -f receptor     ver si está conectado a Mosquitto
docker compose exec web python houston/pruebas_houston.py     pruebas (sin tocar la base)
docker compose down                 detener (los datos quedan en el volumen houston-mongo)
```

- **Dónde está Mosquitto**: en `houston/.env` (no se sube a Git), `HOUSTON_MQTT_HOST=192.168.100.199` (la IP de la
  laptop de la nave). Sin ese archivo usa `host.docker.internal` (Mosquitto en esta misma PC). El puerto es
  `MQTT_PORT` (1883).
- **Usuario de Mosquitto**: en el modo evento hace falta usuario. El receptor usa `MQTT_USER_LECTURA` y
  `MQTT_PASS_LECTURA` (el usuario `equipo`, solo lectura) o, si están vacíos, `MQTT_USER` y `MQTT_PASS`. Se leen de
  `config.local.env` en la raíz, que docker compose pasa a los contenedores si existe.
- Firewall: en la laptop de la nave tiene que estar abierto el 1883 (la regla «Apto hoy» de la sección 3 del README
  principal ya lo abre).

| Servicio | Qué hace | Puerto |
|---|---|---|
| `mongo` | MongoDB 8 de Houston (caché de 256 MB, datos en el volumen `houston-mongo`) | `127.0.0.1:27018` (solo esta PC; 27017 es el de la nave) |
| `receptor` | `receptor.py`: suscrito a `apto/#`, guarda en la base `houston` | — |
| `web` | `servidor.py`: la página y la API | `8090` (`HOUSTON_PUERTO`) |

Sin Docker también funciona: `pip install -r houston/requirements.txt`, un MongoDB en `HOUSTON_MONGO_URI` y
`python houston\receptor.py` y `python houston\servidor.py`.

## Partes (MVC)

| Archivo | Papel |
|---|---|
| `receptor.py` | Se suscribe a `apto/#` y guarda cada mensaje que baja a Tierra en `houston.mensajes`. Cada 2 s escribe su estado en `houston.enlace` (conectado o no, cuántos guardó). |
| `modelo.py` | **Modelo**: consulta la base de Houston y arma las respuestas (una fila por evaluación, la última por tripulante, el resumen del ESP32, el CSV). |
| `controlador.py` | **Controlador**: rutas `GET /api/*` → modelo → JSON o CSV; el resto, archivos de `web/`. |
| `web/` | **Vista**: `index.html`, `houston.css` y `houston.js` (sin frameworks ni internet). Pide los datos cada 5 s. |
| `servidor.py` | Arranca el servidor web. |
| `Dockerfile`, `docker-compose.yml` | Imagen (Python 3.12) y los tres servicios. |

### Qué se ve

- **Enlace**: retraso, último dato de la nave, mensajes en Tierra, mensajes en camino y si el receptor está conectado.
- **Tripulación**: una tarjeta por integrante (`TRIPULACION`) con el color de su última evaluación, la tarea, el
  puntaje, KSS, PVT y pulso; y el conteo por color.
- **Evaluaciones recibidas**: tabla con filtro por persona y período, exportable a CSV.
- **Detalle**: motivos, recomendación, cuestionario, PVT, símbolos, cámara, voz y el resumen del ESP32 de una sesión.
- **Copiloto a bordo**: las últimas preguntas y respuestas.

### API (solo GET)

| Ruta | Devuelve |
|---|---|
| `/api/tablero.json` | Estado del enlace, conteo por color, última evaluación por tripulante, últimas 30 evaluaciones y copiloto |
| `/api/evaluaciones.json?dias=7&persona=bri` | Una fila por evaluación, la más vieja primero (`dias=0` o sin `dias` = todo) |
| `/api/evaluaciones.csv?dias=7&persona=bri` | Lo mismo en CSV |
| `/api/sesion.json?sesion=20261113-193005-bri` | Los mensajes de una sesión; las lecturas del ESP32, resumidas |

Si MongoDB no responde, la API devuelve `{"disponible": false, "motivo"}` y la página lo muestra.

## Qué baja a Tierra (no es una copia exacta de la base de la nave)

- Baja: `evaluacion`, `cuestionario`, `pvt`, `dsst`, `esp32`, `vision`, `voz`, `copiloto` y `control/sesion`.
- No baja: las órdenes (`control/orden_*`), los estados de los módulos (`control/estado_*`, `control/modulos`), las
  preguntas a la estación ni el `semaforo` (el color está en la evaluación).
- Cada documento tiene la forma del registrador (`recibido`, `tema`, `persona`, `tipo`, `simulado`, `reproducido`,
  `datos`) y además `llego_tierra` = `recibido` + `HOUSTON_RETRASO_S` (por defecto `RETRASO_TIERRA_S`, 20 s). Se guarda
  apenas llega, pero la página solo muestra lo que ya «llegó»: un reinicio no pierde lo que viene en camino.
- Al conectarse, el broker entrega los mensajes retenidos (la última evaluación de cada uno, la sesión activa): se
  guardan una sola vez y cuentan como ya llegados.
- Si Houston está apagado, lo que pase en la nave mientras tanto no llega (salvo lo retenido). El registro completo
  sigue en el MongoDB de la nave.
- Los mensajes reproducidos (`registrador/reproducir.py`) se guardan, pero no se muestran.
