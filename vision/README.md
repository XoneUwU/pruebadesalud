# Visión

```
python vision\vision.py --listar                  cámaras disponibles (CAMARA en config.env)
python vision\vision.py --ver                     vista previa en vivo: malla, pulso, EAR, manos y puntaje de lentes
python vision\vision.py --persona bri             una medición de 60 s con ventana (--linea-base, --sin-mqtt)
python vision\vision.py --referencia 72           pulso real (otro aparato) junto al último estimado -> validacion.csv
python vision\vision.py --servicio                espera apto/control/orden_vision (lo arranca iniciar.bat)
python vision\pruebas_vision.py                   prueba con señales sintéticas, sin cámara
python vision\vision.py --persona bri --diagnostico   explica también las aperturas de boca descartadas como bostezo
```

Pulso sin contacto (POS), parpadeos y PERCLOS (EAR), bostezos (también los tapados con la mano, con MediaPipe
Hands) y revisión de lentes antes de medir. Los métodos están al inicio de `vision.py` y en la sección 8 del
README principal.

Para ajustar la detección de lentes: `--ver`, mirar el puntaje arriba a la derecha con y sin lentes, y poner
`LENTES_UMBRAL` entre los dos en `config.local.env`.
