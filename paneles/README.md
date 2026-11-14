# Paneles web

```
python paneles\servidor.py          http://localhost:8080 (y http://IP-de-esta-laptop:8080 desde la red)
python paneles\pruebas_paneles.py   prueba el servidor, /config.js y el JavaScript
```

- `web/estacion.html`: evaluación paso a paso (laptop de la estación).
- `web/tripulacion.html`: semáforo de cada integrante y recomendación (proyector y otras laptops, solo lectura).
- `web/tierra.html`: control de misión con retraso simulado (solo lectura).
- `web/logica.js`: textos, recomendación y PVT sin pantalla (se prueba con Node).
- `web/comun.js`: conexión MQTT por WebSocket e indicador de conexión.
- `web/vendor/mqtt.min.js`: mqtt.js 5.16.1, local, para no depender de internet.

Sin dependencias de Python: solo la biblioteca estándar. Todo lo demás está en la sección 5 del README principal.
