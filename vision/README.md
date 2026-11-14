# Visión

```
python vision\vision.py --listar                  cámaras disponibles (CAMARA en config.env)
python vision\vision.py --ver                     vista previa en vivo: malla, regiones del pulso, pulso y EAR
python vision\vision.py --persona bri             una medición de 60 s con ventana (--linea-base, --sin-mqtt)
python vision\vision.py --referencia 72           pulso real (otro aparato) junto al último estimado -> validacion.csv
python vision\vision.py --servicio                espera apto/control/orden_vision (lo arranca iniciar.bat)
python vision\pruebas_vision.py                   prueba con señales sintéticas, sin cámara
```

Pulso sin contacto (POS), parpadeos y PERCLOS (EAR). Los métodos están al inicio de `vision.py` y en la
sección 8 del README principal.
