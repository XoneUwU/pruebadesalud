# Visión

```
python vision\vision.py --listar                  cámaras disponibles (CAMARA en config.env)
python vision\vision.py --ver                     vista previa en vivo: malla, EAR, manos y puntaje de lentes
python vision\vision.py --persona bri             una medición de 60 s con ventana (--linea-base, --sin-mqtt)
python vision\vision.py --servicio                espera apto/control/orden_vision (lo arranca iniciar.bat)
python vision\pruebas_vision.py                   prueba con señales sintéticas, sin cámara
python vision\vision.py --persona bri --diagnostico   explica también las aperturas de boca descartadas como bostezo
```

Parpadeos y PERCLOS (EAR), bostezos (también los tapados con la mano, con MediaPipe
Hands) y revisión de lentes antes de medir. El pulso por cámara (rPPG) se quitó: el pulso lo mide el ESP32. Los métodos están al inicio de `vision.py` y en la sección 8 del
README principal.

**Qué cámara usa.** La de `CAMARA` (en esta laptop, el celular con DroidCam por cable). Antes de cada medición
rehace «adb forward»; si DroidCam no da video, enciende la pantalla del celular, abre la app (DroidCam o DroidCam
OBS) y prueba unos segundos más. Si igual no responde, mide con la de la laptop (`CAMARA_RESPALDO`, por defecto
`0`; vacío = sin respaldo). Mientras busca publica `{"estado": "buscando", "mensaje"}` en
`apto/control/estado_vision` y la estación espera hasta 30 s antes de empezar la reacción. El resultado lleva
`camara` (la que midió) y, si fue la de respaldo, el motivo en `avisos`. Con el celular bloqueado la app no da
video: conviene dejarlo desbloqueado y con DroidCam en pantalla.

**Video en vivo en la estación.** Con `--servicio`, mientras mide, sirve lo mismo que mostraba la ventana (la
malla de la cara y el conteo en vivo: EAR, parpadeos, bostezos y el tiempo que queda) como MJPEG en
`http://127.0.0.1:8091/video` (`VISION_VIDEO_PUERTO`), a lo sumo 8 cuadros por segundo; el panel de la cámara de
la estación lo muestra («Video en vivo»).

**Cuadros por segundo.** Hacen falta 15 o más (`FPS_MIN`). Dos cosas los bajaban a ~13 durante la prueba de
reacción: Windows 11 manda los procesos en segundo plano a los núcleos de eficiencia (EcoQoS; con el navegador
adelante, la visión queda en segundo plano) y DroidCam manda 1280 x 720. Por eso `vision.py` pide al empezar
velocidad completa (`sin_modo_eficiencia`) y procesa cada cuadro a 640 px de ancho (`PROCESO_ANCHO`). Con la
cámara de la laptop y una cara: 7,3 cuadros por segundo con EcoQoS y 23,5 sin él. Solo escucha en 127.0.0.1: el video
de la cara no sale de esta laptop.

Para ajustar la detección de lentes: `--ver`, mirar el puntaje arriba a la derecha con y sin lentes, y poner
`LENTES_UMBRAL` entre los dos en `config.local.env`.
