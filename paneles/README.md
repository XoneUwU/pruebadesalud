# Paneles web

```
python paneles\servidor.py          http://localhost:8080 (y http://IP-de-esta-laptop:8080 desde la red)
python paneles\pruebas_paneles.py   prueba el servidor, /config.js, el historial y el JavaScript
```

- `web/estacion.html`: estación de monitoreo Becspace (diseño de Claude Design): Panel, Evaluación, Pruebas,
  Resultados, Historial, Configuración y Sistema de diseño (laptop de la estación).
- `web/tripulacion.html`: la misma estación para el proyector y las otras laptops (solo lectura).
- `web/tierra.html`: control de misión con retraso simulado (solo lectura).
- `web/estacion.js`: estado, MQTT, flujo de la evaluación y las pantallas; `web/plantilla.js`: plantillas que
  escapan el texto y actualizan solo lo que cambia; `web/logo.js` y `web/fondo.js`: logo y fondo animados.
- `web/nocturne.css` (sistema de diseño Nocturne) y `web/app.css` (estados y preferencias de la estación).
- `web/logica.js`: textos, recomendación y PVT sin pantalla (se prueba con Node).
- `web/comun.js`: conexión MQTT por WebSocket e indicador de conexión.
- `historial.py`: `/historial.json`, `/historial.csv` y `/sesion.json` desde el MongoDB del registrador (solo lee).
- `web/vendor/`: mqtt.js 5.16.1, íconos Phosphor 2.1.1 y la fuente Inter, locales para no depender de internet
  (origen y SHA-256 en `web/vendor/LEEME.txt`).

`servidor.py` solo usa la biblioteca estándar; el historial necesita además `pymongo` (el mismo del registrador).
Todo lo demás está en la sección 5 del README principal.
