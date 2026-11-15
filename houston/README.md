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
| `web/` | **Vista**: `index.html` y `houston.js` (sin frameworks ni internet), con el **diseño Becspace de la estación**: `nocturne.css`, `app.css`, `plantilla.js`, el logo animado (`logo.js`), el fondo con la Tierra (`fondo.js`), los íconos Phosphor y la fuente Inter se sirven desde `paneles/web` sin copiarlos (lista cerrada en `controlador.py`). Pide los datos cada 5 s. |
| `servidor.py` | Arranca el servidor web. |
| `Dockerfile`, `docker-compose.yml` | Imagen (Python 3.12) y los tres servicios. |

### Qué se ve (tres pantallas, como la estación)

- **Panel**: el enlace (retraso, último dato de la nave, mensajes en Tierra y en camino, si hay señal), el conteo por
  color, una tarjeta por integrante (`TRIPULACION`) con su última evaluación, las últimas recibidas, el aviso de SpO₂
  y lo que respondió el copiloto a bordo.
- **En vivo · a bordo** (en el Panel, se actualiza cada 2 s): cada evaluación en curso (sesión iniciada hace menos de
  30 min) con los pasos que ya llegaron, el pulso, SpO₂ y HRV del ESP32 con su curva, y el resultado apenas llega a
  Tierra (queda 5 min y pasa a la tripulación). Las evaluaciones que vienen en camino muestran «llega en N s». Todo
  va con el retraso de la comunicación: con `HOUSTON_RETRASO_S=0` en `houston/.env` (y `docker compose up -d`) se ve
  al instante.
- **Evaluaciones**: gráfico de evolución (puntaje, PVT, KSS o sueño; con toda la tripulación, un ícono por persona),
  tabla con filtro por periodo y persona, detalle y CSV.
- **Resultado**: el semáforo, la recomendación, los motivos, las horas en la nave y en Tierra, y los indicadores que
  llegaron (ESP32 resumido, PVT, símbolos, cámara, voz y cuestionario).
- Tema oscuro o claro (botón de la barra lateral). `?pantalla=historial` abre directo una pantalla.

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
