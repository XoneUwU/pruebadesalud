"""Análisis por cámara: parpadeos, PERCLOS y bostezos.

Mira la cara con MediaPipe (FaceLandmarker de Tasks), mide los ojos con el EAR y la boca con el MAR, y publica el
resultado en MQTT: apto/{persona}/vision. El pulso lo mide el sensor del ESP32: el pulso por cámara (rPPG) se
quitó porque con la luz de la estación no llegaba a la calidad mínima.

Modos:
  python vision/vision.py --listar                        lista las cámaras
  python vision/vision.py --ver                           vista previa en vivo, sin medir (q o Esc para salir)
  python vision/vision.py --persona bri                   una medición (VISION_SEGUNDOS, con ventana)
  python vision/vision.py --persona bri --linea-base      igual, marcada como línea base
  python vision/vision.py --servicio                      espera órdenes por MQTT (apto/control/orden_vision)

Orden por MQTT (la envía la estación):
  apto/control/orden_vision -> {"accion": "medir", "persona": "bri", "segundos": 60, "linea_base": false, "sesion": "..."}
Mientras mide, abre la ventana de vista previa (la estación le dice a la persona que ahí ve su rostro), publica
apto/control/estado_vision {"estado": "midiendo", "segundos_restantes"} cada 5 s y al final "listo", o "error"
con "motivo". Si antes de empezar ve lentes: {"estado": "lentes", "mensaje", "espera_s"} (pide quitarlos). Al
terminar cierra la ventana y suelta la cámara.

Cámara: CAMARA en config.env (índice 0, 1… o la URL de DroidCam, como http://IP:4747/video). Por cable USB:
CAMARA=http://127.0.0.1:4747/video; antes de cada medición se rehace «adb forward» hacia el celular.

MÉTODOS
  Ojos: EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|), con 6 puntos por ojo. Para parpadeos y PERCLOS cuenta el ojo
  MÁS abierto de los dos: un parpadeo o un cierre son con los dos ojos, y cerrar uno solo (un guiño) no cuenta.
  Para los bostezos se usa el promedio de los dos (al bostezar se achican ambos).
  EAR de ojo abierto = mediana de los primeros 5 s. Parpadeo = EAR por debajo del 60 % del abierto durante al
  menos 2 cuadros seguidos. PERCLOS = fracción del tiempo con la cara visible en que el EAR está por debajo del
  30 % del abierto. Es una aproximación del criterio «ojo cerrado al 80 %» (P80): el EAR no llega a 0 con el ojo
  cerrado por cómo caen los puntos, así que el 30 % del valor abierto se usa como equivalente práctico. No está
  validado clínicamente. Los cuadros con la cabeza inclinada más de 15 grados respecto de los primeros 5 s
  (mirando hacia abajo, por ejemplo a un aparato) no cuentan para los ojos: el párpado baja con la mirada y la
  cámara lo vería como cerrado. Cerrar los ojos no mueve la cabeza, así que un cierre real sí cuenta.
  Bostezos: MAR (apertura de la boca) = promedio de 3 aperturas internas de los labios / ancho entre las
  comisuras internas. Bostezo = MAR >= 0,6 que se mantiene (hasta bajar de 0,45) al menos 1,5 s (hablar abre la
  boca menos y por menos tiempo) y que además muestra al menos una señal de bostezo: los ojos se entrecierran (EAR
  < 85 % del abierto al menos 0,5 s), la boca sigue abierta 2,5 s o más, o se abrió de a poco (de MAR 0,3 a 0,6 en
  0,4 s o más). Un gesto de boca muy abierta al hablar se abre de golpe, dura menos y no achica los ojos: en las
  pruebas reales uno así (MAR 0,93 durante 1,56 s) contaba como bostezo. Durante un bostezo los ojos se achican:
  esos cuadros no cuentan para los parpadeos ni para el PERCLOS. Cada bostezo se explica en la consola (duración,
  MAR, apertura, ojos, mandíbula, mano y por qué se aceptó); con --diagnostico (o VISION_DIAGNOSTICO=1) también
  las aperturas descartadas.
  Bostezos tapados con la mano (en Bolivia, como en otros lugares, se bosteza tapándose la boca): MediaPipe
  Hands (HandLandmarker) busca manos 1 de cada 2 cuadros; «mano en la boca» = 4 o más de sus 21 puntos dentro
  del rectángulo de la boca y la nariz. No se decide con un cuadro sino con la secuencia: por cada vez que la
  mano queda ahí al menos 1 s se mira
    (1) si la boca se abrió en los 1,5 s anteriores a la mano o entre los dedos (MAR >= 0,5 al menos 0,3 s, o
        >= 0,3 al menos 0,6 s: se abre de a poco);
    (2) si la mano tapó antes de poder medir la boca: si la mandíbula bajó mientras la mano estaba (el largo de
        la cara en 3D, de la raíz de la nariz al mentón, suavizado en ~0,5 s, crece un 8 % o más sobre el de
        reposo al menos 0,8 s; en 3D, girar o inclinar la cabeza no lo cambia);
    (2b) o si los ojos quedaron muy cerrados (< 60 % del abierto) al menos 1,5 s con la mano ahí: con la mano
        encima la malla inventa la boca y la mandíbula; lo que se ve es que los pómulos suben y cierran los ojos.
        En pruebas reales con 5 personas, una mano en la boca sin bostezar dejó los ojos al 87 % o más;
    (3) siempre: si los ojos se entrecerraron (EAR suavizado < 85 % del abierto al menos 0,3 s seguidos) desde
        1,5 s antes hasta 0,5 s después de que se va la mano. Es suave a propósito: hay quien casi no achica los
        ojos al bostezar.
  Es bostezo con (3) y además (1), (2) o (2b). Un bostezo visto con la boca abierta y luego tapado cuenta una sola
  vez. El ojo abierto y la mandíbula de reposo de cada mano salen de los 20 s anteriores (sigue a la persona que
  está delante) y las condiciones solo pueden pasar de «no» a «sí»: una decisión tomada no cambia y el contador
  en vivo nunca baja. Cuando la mano se va, la consola explica qué se midió y qué faltó (y en --ver también la ventana), para
  ajustar BOSTEZO_OJOS_FRAC, BOSTEZO_OJOS_S, BOSTEZO_MANDIBULA y BOSTEZO_OJOS_MUY_FRAC en config.env.
  Lentes: MediaPipe no trae un clasificador de lentes. Con la malla se ubica el puente de la nariz entre los ojos
  (puntos 168 y 6), por donde cruza la montura; se endereza la imagen con la línea de los ojos y se mide el borde
  horizontal más marcado ahí (Sobel vertical), dividido por la textura típica de la piel (mejillas y frente):
  sin lentes el puente es piel lisa. Se decide con 2 s de cuadros (60 % o más sobre LENTES_UMBRAL = lentes).
  Antes de medir, si hay lentes, se pide quitarlos (en la ventana y con apto/control/estado_vision "lentes") y
  la medición empieza sola cuando ya no se ven. Si a los LENTES_ESPERA_S siguen puestos, se mide igual con
  "lentes": true y los ojos no cuentan para el semáforo. Lentes sin montura o de montura muy fina pueden no
  detectarse; el umbral se ajusta mirando el puntaje en --ver.
  Avisos: poca luz o demasiada luz (brillo de la frente y las mejillas), cara no detectada más del 20 % del tiempo
  y menos de 15 cuadros por segundo.
Es una sugerencia para apoyar la decisión, no un diagnóstico.
"""
import argparse
import json
import os
import sys
import threading
import time
import warnings
from collections import deque
from datetime import datetime
from pathlib import Path

os.environ.setdefault("GLOG_minloglevel", "2")       # menos mensajes de MediaPipe / TensorFlow Lite
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/

import numpy as np  # noqa: E402

from comun import config  # noqa: E402
from comun.mqtt_cliente import ClienteMQTT, tema  # noqa: E402

CARPETA_DATOS = config.RAIZ / "datos" / "vision"
HISTORIAL = CARPETA_DATOS / "historial.jsonl"
MODELO = config.RAIZ / "modelos" / "face_landmarker.task"
URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
              "face_landmarker.task")
VENTANA = "Vision - Esta apto hoy"

def _real(clave: str, defecto: float) -> float:
    try:
        return float(config.get(clave, "") or defecto)
    except ValueError:
        return defecto


# --- ojos
FS = 30.0                 # cuadros por segundo supuestos si no se puede calcular la duración de un cuadro
CALIBRACION_S = 5.0
PARPADEO_FRAC = 0.60
CERRADO_FRAC = 0.30
PARPADEO_MIN_CUADROS = 2
INCLINACION_MAX = 15.0    # grados de cabeza inclinada (respecto de los primeros 5 s) desde los que no cuentan los ojos
OJO_DER = [33, 160, 158, 133, 153, 144]   # p1..p6 de cada ojo (malla de 478 puntos de MediaPipe)
OJO_IZQ = [362, 385, 387, 263, 373, 380]
# --- boca (bostezos)
BOCA_VERTICAL = [(13, 14), (81, 178), (311, 402)]  # pares labio interno superior / inferior
BOCA_COMISURAS = (78, 308)                          # comisuras internas
BOSTEZO_MAR = 0.6         # boca muy abierta
BOSTEZO_FIN_MAR = 0.45    # se considera cerrada otra vez por debajo de esto (histéresis)
BOSTEZO_MIN_S = 1.5       # hablar abre la boca menos tiempo
# Además, una apertura así tiene que mostrar al menos UNA señal de bostezo (si no, es un gesto: en las trazas reales
# un gesto de boca muy abierta, MAR 0,93 durante 1,56 s, contaba como bostezo). Comparadas en las trazas reales:
#   bostezos simulados -> abiertos 2,3 a 4,8 s, abren de a poco (0,43 a 3,2 s de MAR 0,3 a 0,6), ojos < 85 % 1,4 s o más;
#   gestos y habla     -> abiertos 0,5 a 1,6 s, abren de golpe (0,14 a 0,29 s), ojos casi siempre al 90-120 %.
# Las señales (basta una; las tres solo crecen con el tiempo, así que el contador en vivo no baja):
BOSTEZO_VISTO_OJOS_S = _real("BOSTEZO_VISTO_OJOS_S", 0.5)  # ojos < OJOS_BOSTEZO_FRAC del abierto este tiempo seguido
BOSTEZO_LARGO_S = _real("BOSTEZO_LARGO_S", 2.5)            # o la boca sigue abierta este tiempo (sin mirar los ojos)
BOSTEZO_SUBIDA_S = _real("BOSTEZO_SUBIDA_S", 0.4)          # o se abrió de a poco: de MAR_ABRIENDO a BOSTEZO_MAR
BOSTEZO_DIAGNOSTICO_S = 0.5  # en modo diagnóstico se explican las aperturas de boca desde esta duración
DIAGNOSTICO = config.get("VISION_DIAGNOSTICO", "0").strip() not in ("", "0")  # o --diagnostico
# --- bostezos tapados con la mano (MediaPipe Hands)
MODELO_MANOS = config.RAIZ / "modelos" / "hand_landmarker.task"
URL_MODELO_MANOS = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/"
                    "hand_landmarker.task")
MANOS_CADA = 2            # las manos se buscan 1 de cada 2 cuadros (en el otro se usa el último resultado)
MANO_PUNTOS_MIN = 4       # puntos de la mano (de 21) dentro de la zona de la boca y la nariz
MANO_HUECO_S = 0.4        # huecos más cortos con la mano en la boca se rellenan (la detección parpadea)
MANO_MIN_S = 1.0          # menos tiempo con la mano en la boca no es un bostezo tapado
PREVIO_S = 1.5            # ventana de antes de que llegue la mano
MAR_PREVIO = 0.5          # boca «significativamente abierta» justo antes de taparla (o entre los dedos)...
MAR_PREVIO_S = 0.3        # ...al menos este tiempo (al toser se abre menos tiempo)
MAR_ABRIENDO = 0.3        # o abriéndose de a poco: MAR >= 0,3...
MAR_ABRIENDO_S = 0.6      # ...al menos este tiempo seguido (al hablar abre y cierra varias veces por segundo)
# Ojos entrecerrados = EAR (suavizado con la mediana de 5 cuadros: quita el temblor de la malla) por debajo del
# 85 % del ojo abierto, al menos 0,3 s seguidos. Hay quien casi no achica los ojos al bostezar: por eso es suave.
OJOS_BOSTEZO_FRAC = _real("BOSTEZO_OJOS_FRAC", 0.85)
OJOS_BOSTEZO_S = _real("BOSTEZO_OJOS_S", 0.3)
OJOS_DESPUES_S = 0.5      # los ojos se miran hasta 0,5 s después de que se va la mano
SUAVIZADO = 5             # cuadros de la mediana móvil del EAR y de la mandíbula
MANO_DIAGNOSTICO_S = 0.3  # desde aquí una mano en la boca sale en el diagnóstico (aunque no llegue a MANO_MIN_S)
# La mandíbula baja: la cara (suavizada) se alarga un 8 % o más sobre la de reposo... Con la mano encima, MediaPipe
# tiende a dibujar la boca cerrada y la mandíbula sube poco (en pruebas reales, +6 a +12 % durante el bostezo).
MANDIBULA_SUBE = _real("BOSTEZO_MANDIBULA", 0.08)
MANDIBULA_MIN_S = 0.8     # ...al menos este tiempo seguido (al hablar sube y baja más rápido)
# O bien: ojos muy cerrados (< 60 % del abierto) al menos 1,5 s seguidos con la mano en la boca. Con la mano encima,
# la malla inventa la parte de abajo de la cara (dibuja la boca cerrada y la mandíbula casi quieta); lo que se ve
# es la de arriba: al bostezar suben los pómulos y cierran los ojos desde abajo. En las pruebas reales (5 personas),
# una mano en la boca sin bostezar dejó los ojos al 87-180 %, y los bostezos tapados, por debajo del 60 % varios s.
OJOS_MUY_FRAC = _real("BOSTEZO_OJOS_MUY_FRAC", 0.60)
OJOS_MUY_S = 1.5
SUAVIZADO_MANDIBULA = 15  # cuadros (~0,5 s): el bostezo baja la mandíbula despacio; al hablar sube y baja rápido
# El ojo abierto y la mandíbula de reposo de cada mano en la boca salen de los 20 s ANTERIORES a la mano (sin mano y,
# para la mandíbula, con la boca cerrada): la decisión no cambia con lo que pase después (el contador no baja) y
# sigue a la persona que está delante (en --ver pueden pasar varias). Si antes hay menos de 40 cuadros de reposo,
# se usan los primeros 40 de la medición; si todavía no hay, la mano queda pendiente.
BASE_VENTANA_S = 20.0
BASE_MIN_CUADROS = 40
UNIR_S = 1.0              # dos detecciones a menos de 1 s son el mismo bostezo
# --- lentes (ajustables en config.env)
LENTES_REVISAR = config.get("LENTES_REVISAR", "1").strip() != "0"
LENTES_UMBRAL = _real("LENTES_UMBRAL", 4.0)      # puntaje desde el que un cuadro «tiene lentes»
LENTES_ESPERA_S = _real("LENTES_ESPERA_S", 30.0)  # cuánto se espera a que se los quiten
LENTES_REVISION_S = 2.0   # se decide con los cuadros de los últimos 2 s, no con uno
LENTES_FRAC = 0.6         # hay lentes si el 60 % o más de esos cuadros pasa el umbral...
LENTES_LIBRE_FRAC = 0.2   # ...y ya no hay cuando baja al 20 % o menos
MENSAJE_LENTES = ("Se ven lentes: quítatelos para continuar con la medición. Empieza sola cuando ya no se vean.")
# --- cámara de respaldo: si la de CAMARA (el celular) no da video, se mide con esta (índice de la cámara de la
# laptop; vacío = sin respaldo). Solo una: el índice 1 suele ser la cámara virtual de DroidCam, que da una imagen fija.
CAMARA_RESPALDO = config.get("CAMARA_RESPALDO", "0").strip()
DROIDCAM_APPS = ("com.dev47apps.droidcam", "com.dev47apps.obsdroidcam")  # DroidCam y DroidCam OBS
DROIDCAM_ESPERA_S = 8.0  # al abrir la app desde la laptop: lo que se espera a que arranque
# --- avisos
LUZ_MIN, LUZ_MAX = 60, 210                # brillo medio de la piel (0 a 255)
SATURADO_MAX = 0.05                       # fracción de píxeles de piel saturados
CARA_MIN_PCT = 80
FPS_MIN = 15


class ErrorMedicion(Exception):
    """La medición no se pudo hacer (cámara, cara, cancelada); el mensaje es el motivo."""


# ================================================================ cálculos (sin cámara: se prueban con señales)
def ear(ojo: np.ndarray) -> float:
    """EAR de un ojo: 6 puntos (x, y) en el orden p1..p6."""
    p1, p2, p3, p4, p5, p6 = ojo
    ancho = np.linalg.norm(p1 - p4)
    return float((np.linalg.norm(p2 - p6) + np.linalg.norm(p3 - p5)) / (2 * ancho)) if ancho > 0 else float("nan")


def ear_ojos(pts: np.ndarray) -> tuple[float, float]:
    """EAR de cada ojo por separado: (derecho, izquierdo)."""
    return ear(pts[OJO_DER]), ear(pts[OJO_IZQ])


def ear_parpadeo(ear_der, ear_izq) -> np.ndarray:
    """EAR para parpadeos y PERCLOS: el del ojo MÁS abierto de los dos. Así un parpadeo o un cierre son con los dos
    ojos, y cerrar uno solo (un guiño) no cuenta. Si falta uno, vale el otro."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.fmax(np.asarray(ear_der, float), np.asarray(ear_izq, float))


def ear_cara(pts: np.ndarray) -> float:
    return (ear(pts[OJO_DER]) + ear(pts[OJO_IZQ])) / 2


def mar(pts: np.ndarray) -> float:
    """MAR (apertura de la boca) = promedio de 3 aperturas verticales internas / ancho entre comisuras internas."""
    ancho = np.linalg.norm(pts[BOCA_COMISURAS[0]] - pts[BOCA_COMISURAS[1]])
    if ancho <= 0:
        return float("nan")
    return float(np.mean([np.linalg.norm(pts[a] - pts[b]) for a, b in BOCA_VERTICAL]) / ancho)


def mandibula(pts: np.ndarray, z: np.ndarray | None = None) -> float:
    """Largo de la cara (raíz de la nariz, punto 168, al mentón, 152) / distancia entre los rabillos externos de los
    ojos. Sube cuando baja la mandíbula, aunque la mano tape los labios. Con la profundidad z de la malla (en la misma
    escala que x) se mide en 3D: girar o inclinar la cabeza no la cambia (en la imagen plana, girar la cabeza acorta
    la distancia entre los ojos y la cara parece más larga)."""
    p = np.column_stack([pts[:, :2], z]) if z is not None and len(z) == len(pts) else pts[:, :2]
    escala = float(np.linalg.norm(p[33] - p[263]))
    return float(np.linalg.norm(p[168] - p[152]) / escala) if escala > 0 else float("nan")


def zona_boca(pts: np.ndarray) -> tuple[float, float, float, float]:
    """Rectángulo (x0, y0, x1, y1) de la boca y la nariz, donde va la mano al taparse un bostezo."""
    e = float(np.linalg.norm(pts[33] - pts[263]))
    cx = (pts[61][0] + pts[291][0]) / 2
    return cx - 0.6 * e, pts[1][1] - 0.15 * e, cx + 0.6 * e, pts[152][1] + 0.1 * e


def mano_en_boca(zona, manos) -> bool:
    """¿Alguna mano tiene al menos MANO_PUNTOS_MIN de sus 21 puntos dentro de la zona de la boca?"""
    x0, y0, x1, y1 = zona
    for m in manos:
        m = np.asarray(m, float)
        if (((m[:, 0] >= x0) & (m[:, 0] <= x1) & (m[:, 1] >= y0) & (m[:, 1] <= y1)).sum()) >= MANO_PUNTOS_MIN:
            return True
    return False


def _tramos(mascara) -> list[tuple[int, int]]:
    """Tramos seguidos de True: [(inicio, fin_exclusivo)]."""
    m = np.concatenate(([False], np.asarray(mascara, bool), [False]))
    cambios = np.flatnonzero(m[1:] != m[:-1])
    return [(int(a), int(b)) for a, b in zip(cambios[::2], cambios[1::2])]


def _racha_s(t: np.ndarray, mascara) -> float:
    """Duración (s) del tramo seguido de True más largo."""
    return max((float(t[b - 1] - t[a]) for a, b in _tramos(mascara)), default=0.0)


def _rellenar(t: np.ndarray, mascara, hueco_s: float) -> np.ndarray:
    """Une los tramos de True separados por huecos de hueco_s o menos."""
    m = np.asarray(mascara, bool).copy()
    tramos = _tramos(m)
    for (_, b1), (a2, _) in zip(tramos, tramos[1:]):
        if t[a2] - t[b1 - 1] <= hueco_s:
            m[b1:a2] = True
    return m


def _aperturas(t: np.ndarray, mares: np.ndarray, min_s: float = BOSTEZO_MIN_S) -> list[tuple[int, int]]:
    """Tramos (índices) con MAR >= BOSTEZO_MAR que se mantiene (hasta bajar de BOSTEZO_FIN_MAR, o hasta perder la
    cara) min_s o más. Un tramo que sigue abierto al final de los datos también sale (para el contador en vivo)."""
    tramos, inicio = [], None
    for i, m in enumerate(mares):
        abierta = np.isfinite(m) and (m >= BOSTEZO_MAR or (inicio is not None and m >= BOSTEZO_FIN_MAR))
        if abierta and inicio is None:
            inicio = i
        elif not abierta and inicio is not None:
            if t[i - 1] - t[inicio] >= min_s:
                tramos.append((inicio, i))
            inicio = None
    if inicio is not None and t[-1] - t[inicio] >= min_s:
        tramos.append((inicio, len(t)))
    return tramos


def _suavizar(x, n: int = SUAVIZADO, causal: bool = False) -> np.ndarray:
    """Mediana móvil de n cuadros (sin contar los NaN): quita el temblor de la malla sin correr los cambios.
    `causal`: solo con los n cuadros hasta ese (no los siguientes): lo ya calculado no cambia al llegar más cuadros."""
    x = np.asarray(x, float)
    if len(x) < n:
        return x.copy()
    borde = (n - 1, 0) if causal else n // 2
    ventanas = np.lib.stride_tricks.sliding_window_view(np.pad(x, borde, mode="edge"), n)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # ventanas sin ningún dato -> NaN
        return np.nanmedian(ventanas, axis=1)


def _base(t: np.ndarray, valores: np.ndarray, reposo: np.ndarray, ta: float) -> float | None:
    """Mediana del reposo de los BASE_VENTANA_S anteriores a ta (o de los primeros BASE_MIN_CUADROS de reposo)."""
    antes = reposo & (t >= ta - BASE_VENTANA_S) & (t < ta)
    if antes.sum() >= BASE_MIN_CUADROS:
        return float(np.median(valores[antes]))
    primeros = np.flatnonzero(reposo)[:BASE_MIN_CUADROS]
    return float(np.median(valores[primeros])) if len(primeros) >= BASE_MIN_CUADROS else None


def episodios_boca(t, mares, ears=None, manos=None, mandibulas=None,
                   min_s: float = BOSTEZO_MIN_S) -> list[dict]:
    """Cada apertura de boca a la vista (MAR >= BOSTEZO_MAR sostenido, ver _aperturas) de min_s o más, con lo que se
    midió y si es un bostezo. `mares` ya sin los cuadros con la mano en la boca (NaN). Es bostezo si dura
    BOSTEZO_MIN_S y además muestra al menos una señal de bostezo:
      (a) ojos entrecerrados: EAR (mediana causal de 5 cuadros) < OJOS_BOSTEZO_FRAC del abierto al menos
          BOSTEZO_VISTO_OJOS_S seguidos, desde que la boca empezó a abrirse;
      (b) o la boca sigue abierta BOSTEZO_LARGO_S (hay quien casi no achica los ojos);
      (c) o se abrió de a poco: de MAR < MAR_ABRIENDO a MAR >= BOSTEZO_MAR en BOSTEZO_SUBIDA_S o más (un gesto o el
          habla abren de golpe). Si antes de abrirse no se vio la cara (o empieza la medición), no se sabe: no vale.
    La mandíbula se mide solo para el diagnóstico (sube igual en un gesto que en un bostezo). Todo se calcula con lo
    que pasó hasta cada cuadro, y (a), (b) y (c) solo pueden pasar de «no» a «sí»: el contador en vivo no baja."""
    t, mares = np.asarray(t, float), np.asarray(mares, float)
    n = len(t)
    if len(mares) != n:  # sin la boca medida cuadro a cuadro
        return []
    con_ojos = ears is not None and len(ears) == n
    ears = np.asarray(ears, float) if con_ojos else np.full(n, np.nan)
    mano = np.asarray(manos, float) if manos is not None and len(manos) == n else np.zeros(n)
    mand = np.asarray(mandibulas, float) if mandibulas is not None and len(mandibulas) == n else np.full(n, np.nan)
    cerrada = np.nan_to_num(mares, nan=1.0) < BOSTEZO_FIN_MAR
    reposo_ojos = np.isfinite(ears) & (mano != 1) & cerrada
    reposo_mand = np.isfinite(mand) & (mano != 1) & (np.nan_to_num(mares, nan=1.0) < MAR_ABRIENDO)
    ears_s = _suavizar(ears, causal=True)
    salida = []
    for a, b in _aperturas(t, mares, min_s):
        ta, tb = float(t[a]), float(t[b - 1])
        k = a  # desde dónde se abre: el último cuadro (con cara) con la boca casi cerrada
        while k > 0 and np.isfinite(mares[k - 1]) and mares[k - 1] >= MAR_ABRIENDO:
            k -= 1
        conocida = k > 0 and np.isfinite(mares[k - 1])  # se vio la boca cerrada antes de abrirse
        subida = ta - float(t[k - 1]) if conocida else None
        abierto = _base(t, ears, reposo_ojos, ta) if con_ojos else None
        ojos_pct, ojos_s = None, 0.0
        if abierto:
            vistos = ears_s[k:b][np.isfinite(ears_s[k:b])]
            ojos_pct = float(vistos.min() / abierto * 100) if len(vistos) else None
            ojos_s = _racha_s(t[k:b], np.isfinite(ears_s[k:b]) & (ears_s[k:b] < OJOS_BOSTEZO_FRAC * abierto))
        base_mand = _base(t, mand, reposo_mand, ta)
        tramo_mand = mand[a:b][np.isfinite(mand[a:b])]
        mand_pct = float(tramo_mand.max() / base_mand * 100 - 100) if base_mand and len(tramo_mand) else None
        tramo = mares[a:b]
        dur = tb - ta
        ep = {"inicio": ta, "fin": tb, "tramo": (a, b), "duracion_s": dur, "abierta": b == n, "subida_s": subida,
              "mar_max": float(np.nanmax(tramo)), "mar_mediana": float(np.nanmedian(tramo)),
              "mar_inicio": float(tramo[0]), "mar_fin": float(tramo[-1]),
              "ojos_pct": ojos_pct, "ojos_s": ojos_s, "con_ojos": abierto is not None, "mandibula_pct": mand_pct,
              "mano_despues": bool((mano[b:] == 1)[t[b:] <= tb + UNIR_S].any()) if b < n else False,
              "dur_ok": dur >= BOSTEZO_MIN_S, "ojos_ok": ojos_s >= BOSTEZO_VISTO_OJOS_S,
              "largo_ok": dur >= BOSTEZO_LARGO_S, "subida_ok": subida is not None and subida >= BOSTEZO_SUBIDA_S}
        ep["bostezo"] = ep["dur_ok"] and (ep["ojos_ok"] or ep["largo_ok"] or ep["subida_ok"])
        salida.append(ep)
    return salida


def _bostezos_abiertos(t: np.ndarray, mares: np.ndarray, ears=None, mandibulas=None,
                       manos=None) -> list[tuple[int, int]]:
    """Tramos (índices) de los bostezos con la boca a la vista (ver episodios_boca)."""
    return [e["tramo"] for e in episodios_boca(t, mares, ears, manos, mandibulas) if e["bostezo"]]


def texto_bostezo(ep: dict) -> str:
    """Una apertura de boca explicada para la consola: lo medido, las señales y por qué se aceptó o se descartó."""
    def num(x, fmt):
        return "?" if x is None else format(x, fmt)
    senales = [nombre for nombre, ok in (("ojos entrecerrados", ep["ojos_ok"]), ("boca abierta largo", ep["largo_ok"]),
                                         ("apertura gradual", ep["subida_ok"])) if ok]
    if ep["bostezo"]:
        final = "BOSTEZO (" + ", ".join(senales) + ")"
    elif not ep["dur_ok"]:
        final = f"descartado: abierta menos de {BOSTEZO_MIN_S:g} s"
    else:
        final = (f"descartado: sin señal de bostezo (ojos < {OJOS_BOSTEZO_FRAC * 100:.0f} % menos de "
                 f"{BOSTEZO_VISTO_OJOS_S:g} s{'' if ep['con_ojos'] else ' o sin ojos para comparar'}, abierta menos de "
                 f"{BOSTEZO_LARGO_S:g} s y apertura de golpe)")
    return (f"[vision] Boca abierta a los {ep['inicio']:.1f} s durante {ep['duracion_s']:.1f} s"
            f"{' (sigue abierta)' if ep['abierta'] else ''} | MAR {ep['mar_inicio']:.2f} -> máx {ep['mar_max']:.2f} "
            f"(mediana {ep['mar_mediana']:.2f}) -> {ep['mar_fin']:.2f} | se abrió en {num(ep['subida_s'], '.2f')} s (pide "
            f"{BOSTEZO_SUBIDA_S:g}) | ojos hasta el {num(ep['ojos_pct'], '.0f')} % del abierto, {ep['ojos_s']:.1f} s bajo "
            f"el {OJOS_BOSTEZO_FRAC * 100:.0f} % (pide {BOSTEZO_VISTO_OJOS_S:g}) | mandíbula "
            f"{num(ep['mandibula_pct'], '+.0f')} % | mano en la boca después: {'sí' if ep['mano_despues'] else 'no'} "
            f"-> {final}")


def episodios_mano(t, mares, ears, manos, mandibulas) -> list[dict]:
    """Cada vez que la mano quedó en la zona de la boca (los huecos cortos de la detección se rellenan), lo que se
    midió y si es un bostezo tapado. Condiciones:
      (0) la mano queda al menos MANO_MIN_S;
      (1) boca abierta antes de la mano (en los PREVIO_S anteriores) o entre los dedos: MAR >= MAR_PREVIO al menos
          MAR_PREVIO_S, o MAR >= MAR_ABRIENDO al menos MAR_ABRIENDO_S seguidos (se abre de a poco);
      (2) o, si la mano tapó antes de poder medir la boca, la mandíbula bajó: con la mano ahí, el largo de la cara
          (suavizado) supera en MANDIBULA_SUBE el de reposo (sin mano y con la boca cerrada) MANDIBULA_MIN_S;
      (3) ojos entrecerrados: EAR suavizado < OJOS_BOSTEZO_FRAC del abierto al menos OJOS_BOSTEZO_S seguidos, entre
          PREVIO_S antes de la mano y OJOS_DESPUES_S después de que se va;
      (4) o ojos muy cerrados: con la mano ahí (hasta OJOS_DESPUES_S después), EAR suavizado < OJOS_MUY_FRAC del
          abierto al menos OJOS_MUY_S seguidos (los pómulos suben y cierran los ojos; la mandíbula no se ve).
    Es bostezo con (0), (3) y además (1), (2) o (4). El ojo abierto y la mandíbula de reposo salen de antes de la
    mano (BASE_VENTANA_S), y cada condición es una racha que solo puede crecer: lo que pase después no cambia la
    decisión, así que el contador en vivo nunca baja. Salen también las manos de MANO_DIAGNOSTICO_S o más, para ver
    qué faltó; "pendiente" si aún no hay reposo para comparar."""
    t = np.asarray(t, float)
    mares, ears = np.asarray(mares, float), np.asarray(ears, float)
    manos, mand = np.asarray(manos, float), np.asarray(mandibulas, float)
    en_boca = _rellenar(t, manos == 1, MANO_HUECO_S)
    reposo_ojos = np.isfinite(ears) & ~en_boca
    reposo_mand = np.isfinite(mand) & ~en_boca & (np.nan_to_num(mares, nan=1.0) < 0.3)
    ears_s, mand_s = _suavizar(ears), _suavizar(mand, SUAVIZADO_MANDIBULA)
    mar0 = np.nan_to_num(mares, nan=0.0)
    muy_abierta, abriendo = mar0 >= MAR_PREVIO, mar0 >= MAR_ABRIENDO
    salida = []
    for a, b in _tramos(en_boca):
        ta, tb = float(t[a]), float(t[b - 1])
        if tb - ta < MANO_DIAGNOSTICO_S:
            continue
        abierto, base_mand = _base(t, ears, reposo_ojos, ta), _base(t, mand, reposo_mand, ta)
        ep = {"mano_desde": ta, "fin": tb, "mano_s": tb - ta, "pendiente": abierto is None or abierto <= 0,
              "bostezo": False, "inicio": ta}
        if ep["pendiente"]:
            salida.append(ep)
            continue
        ventana_boca = (t >= ta - PREVIO_S) & (t <= tb)  # antes de la mano y entre los dedos
        boca_s = _racha_s(t, muy_abierta & ventana_boca)
        abriendo_s = _racha_s(t, abriendo & ventana_boca)
        con_mano = np.zeros(len(t), bool)
        con_mano[a:b] = True
        mand_pct, mand_dur = None, 0.0
        if base_mand:
            rel = mand_s[con_mano & np.isfinite(mand_s)] / base_mand - 1
            mand_pct = float(rel.max() * 100) if len(rel) else None
            mand_dur = _racha_s(t, con_mano & np.isfinite(mand_s) & (mand_s >= base_mand * (1 + MANDIBULA_SUBE)))
        ventana_ojos = (t >= ta - PREVIO_S) & (t <= tb + OJOS_DESPUES_S)
        vistos = ears_s[ventana_ojos & np.isfinite(ears_s)]
        ojos_pct = float(vistos.min() / abierto * 100) if len(vistos) else None
        ojos_dur = _racha_s(t, np.isfinite(ears_s) & (ears_s < OJOS_BOSTEZO_FRAC * abierto) & ventana_ojos)
        muy_cerrados = np.isfinite(ears_s) & (ears_s < OJOS_MUY_FRAC * abierto) & (t >= ta) & (t <= tb + OJOS_DESPUES_S)
        ojos_muy_dur = _racha_s(t, muy_cerrados)
        ep.update({"boca_previa_s": boca_s, "boca_abriendo_s": abriendo_s, "mandibula_pct": mand_pct,
                   "mandibula_s": mand_dur, "ojos_pct": ojos_pct, "ojos_s": ojos_dur, "ojos_muy_s": ojos_muy_dur,
                   "mano_ok": tb - ta >= MANO_MIN_S,
                   "boca_ok": boca_s >= MAR_PREVIO_S or abriendo_s >= MAR_ABRIENDO_S,
                   "mandibula_ok": mand_dur >= MANDIBULA_MIN_S, "ojos_ok": ojos_dur >= OJOS_BOSTEZO_S,
                   "ojos_cerrados_ok": ojos_muy_dur >= OJOS_MUY_S})
        ep["bostezo"] = ep["mano_ok"] and ep["ojos_ok"] and (ep["boca_ok"] or ep["mandibula_ok"]
                                                             or ep["ojos_cerrados_ok"])
        ep["inicio"] = ta - PREVIO_S if ep["boca_ok"] else ta
        salida.append(ep)
    return salida


def bostezos_tapados(t, mares, ears, manos, mandibulas) -> list[tuple[float, float]]:
    """Bostezos tapados con la mano -> [(inicio, fin)] en segundos (ver episodios_mano)."""
    return [(e["inicio"], e["fin"]) for e in episodios_mano(t, mares, ears, manos, mandibulas) if e["bostezo"]]


def texto_episodio(ep: dict, corto: bool = False) -> str:
    """Una mano en la boca explicada: qué se midió, qué pide cada condición y qué faltó. `corto`: sin tildes, para
    la ventana de OpenCV."""
    if ep.get("pendiente"):
        return (f"MANO {ep['mano_s']:.1f}s | todavia sin reposo para comparar" if corto else
                f"[vision] Mano en la boca {ep['mano_s']:.1f} s: todavía no hay {BASE_MIN_CUADROS} cuadros de reposo para "
                f"comparar; se decide después")
    mand = f"{ep['mandibula_pct']:+.0f}" if ep["mandibula_pct"] is not None else "?"
    ojos = f"{ep['ojos_pct']:.0f}" if ep["ojos_pct"] is not None else "?"
    if corto:
        return (f"MANO {ep['mano_s']:.1f}s | boca {ep['boca_previa_s']:.1f}s/{ep['boca_abriendo_s']:.1f}s | mandibula "
                f"{mand}% {ep['mandibula_s']:.1f}s | ojos {ojos}% {ep['ojos_s']:.1f}s, muy cerrados {ep['ojos_muy_s']:.1f}s"
                f" -> {'BOSTEZO' if ep['bostezo'] else 'no'}")
    faltan = []
    if not ep["mano_ok"]:
        faltan.append(f"la mano estuvo menos de {MANO_MIN_S:g} s")
    if not ep["ojos_ok"]:
        faltan.append("los ojos casi no se entrecerraron")
    if not (ep["boca_ok"] or ep["mandibula_ok"] or ep["ojos_cerrados_ok"]):
        faltan.append("no se vio la boca abierta (antes o entre los dedos), ni bajar la mandíbula, ni los ojos muy "
                      "cerrados")
    final = "BOSTEZO" if ep["bostezo"] else "no es bostezo: " + "; ".join(faltan)
    return (f"[vision] Mano en la boca {ep['mano_s']:.1f} s | boca abierta {ep['boca_previa_s']:.1f} s con MAR >= "
            f"{MAR_PREVIO:g} (pide {MAR_PREVIO_S:g}) o {ep['boca_abriendo_s']:.1f} s con >= {MAR_ABRIENDO:g} (pide "
            f"{MAR_ABRIENDO_S:g}) | mandíbula hasta {mand} %, {ep['mandibula_s']:.1f} s sobre +{MANDIBULA_SUBE * 100:.0f} % "
            f"(pide {MANDIBULA_MIN_S:g} s) | ojos hasta el {ojos} % del abierto, {ep['ojos_s']:.1f} s bajo el "
            f"{OJOS_BOSTEZO_FRAC * 100:.0f} % (pide {OJOS_BOSTEZO_S:g} s) y {ep['ojos_muy_s']:.1f} s bajo el "
            f"{OJOS_MUY_FRAC * 100:.0f} % (pide {OJOS_MUY_S:g} s) -> {final}")


def explicar_bostezos(registro: "Registro", explicados: set, hasta: float, con_manos: bool = True) -> list[str]:
    """Textos (texto_bostezo) de las aperturas de boca a la vista que ya se cerraron antes de `hasta` (con
    hasta=inf, también la que sigue abierta al final) y aún no se explicaron: los bostezos siempre; las descartadas
    solo en modo diagnóstico (DIAGNOSTICO o --diagnostico), para no llenar la consola."""
    n = len(registro.t)
    if n < 2:
        return []
    t, vista = np.asarray(registro.t, float), np.asarray(registro.mar, float).copy()
    manos = np.asarray(registro.mano, float) if con_manos and len(registro.mano) == n else None
    if manos is not None:
        vista[manos == 1] = np.nan
    ears = registro.ear if len(registro.ear) == n else None
    mand = registro.mandibula if len(registro.mandibula) == n else None
    lineas = []
    for ep in episodios_boca(t, vista, ears, manos, mand, BOSTEZO_DIAGNOSTICO_S if DIAGNOSTICO else BOSTEZO_MIN_S):
        clave = round(ep["inicio"], 2)
        terminada = hasta == float("inf") or (not ep["abierta"] and ep["fin"] < hasta)
        if terminada and clave not in explicados and (ep["bostezo"] or DIAGNOSTICO):
            explicados.add(clave)
            lineas.append(texto_bostezo(ep))
    return lineas


def _unir(tramos: list[tuple[float, float, bool]]) -> list[tuple[float, float, bool]]:
    """(inicio, fin, tapado) que se solapan o están a menos de UNIR_S -> uno solo (tapado si alguno lo fue)."""
    salida: list[tuple[float, float, bool]] = []
    for ini, fin, tapado in sorted(tramos):
        if salida and ini - salida[-1][1] <= UNIR_S:
            p = salida[-1]
            salida[-1] = (p[0], max(p[1], fin), p[2] or tapado)
        else:
            salida.append((ini, fin, tapado))
    return salida


def analizar_boca(t: np.ndarray, mares: np.ndarray, ears=None, manos=None, mandibulas=None) -> dict:
    """Bostezos con la boca a la vista (MAR >= BOSTEZO_MAR sostenido BOSTEZO_MIN_S, con una señal de bostezo: ver
    episodios_boca) y, si se dan por cuadro los ojos, la mano en la boca (1, 0 o NaN) y la mandíbula, también los
    tapados con la mano (bostezos_tapados). Los que se solapan cuentan una vez. Con la mano encima el MAR no sirve:
    esos cuadros no cuentan para la boca. Sin los ojos, los de boca a la vista solo cuentan si son largos o graduales.

    Devuelve bostezos, bostezos_tapados, bostezos_min y `durante` (máscara de los cuadros de cada bostezo)."""
    t, mares = np.asarray(t, float), np.asarray(mares, float)
    n = len(t)
    con_manos = manos is not None and len(manos) == n and ears is not None and len(ears) == n
    vista = mares.copy()
    if con_manos:
        vista[np.asarray(manos, float) == 1] = np.nan
    tramos = [(float(t[a]), float(t[b - 1]), False)
              for a, b in _bostezos_abiertos(t, vista, ears, mandibulas, manos if con_manos else None)]
    if con_manos and n > 1:
        mand = mandibulas if mandibulas is not None and len(mandibulas) == n else np.full(n, np.nan)
        tramos += [(a, b, True) for a, b in bostezos_tapados(t, mares, ears, manos, mand)]
    unidos = _unir(tramos)
    durante = np.zeros(n, bool)
    for ini, fin, _ in unidos:
        durante |= (t >= ini) & (t <= fin)
    tiempo_cara = float(np.isfinite(mares).sum() / max(n, 1) * (t[-1] - t[0])) if n > 1 else 0.0
    bostezos = len(unidos)
    return {"bostezos": bostezos, "bostezos_tapados": sum(1 for *_, tap in unidos if tap),
            "bostezos_min": round(bostezos / (tiempo_cara / 60), 1) if tiempo_cara > 0 else None,
            "durante": durante}


def puntaje_lentes(cuadro_bgr: np.ndarray, pts: np.ndarray) -> float | None:
    """Indicio de lentes en un cuadro: el borde horizontal más marcado en el puente de la nariz (entre los ojos, por
    donde cruza la montura) dividido por la textura típica de la piel (mejillas y frente). Sin lentes el puente es
    piel lisa (cerca de 1 a 2); con montura sube mucho. La imagen se endereza antes con la línea de los ojos.
    None si la cara es muy chica para ver una montura."""
    import cv2
    e = float(np.linalg.norm(pts[33] - pts[263]))
    if e < 40:
        return None
    dx, dy = pts[263] - pts[33]
    centro = (float(pts[168][0]), float(pts[168][1]))
    lado = int(2.4 * e)
    giro = cv2.getRotationMatrix2D(centro, float(np.degrees(np.arctan2(dy, dx))), 1.0)
    giro[:, 2] += (lado / 2 - centro[0], lado / 2 - centro[1])  # el punto 168 queda en el centro del recorte
    gris = cv2.cvtColor(cuadro_bgr, cv2.COLOR_BGR2GRAY) if cuadro_bgr.ndim == 3 else cuadro_bgr
    recorte = cv2.warpAffine(gris, giro, (lado, lado), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    gy = np.abs(cv2.Sobel(cv2.GaussianBlur(recorte, (3, 3), 0).astype(np.float32), cv2.CV_32F, 0, 1, ksize=3))
    p = pts @ giro[:, :2].T + giro[:, 2]  # los puntos, en el recorte enderezado

    def filas(x0, y0, x1, y1):  # promedio de |Gy| de cada fila del rectángulo
        x0, y0, x1, y1 = max(0, int(x0)), max(0, int(y0)), min(lado, int(x1)), min(lado, int(y1))
        return gy[y0:y1, x0:x1].mean(axis=1) if x1 - x0 >= 4 and y1 - y0 >= 3 else None

    cx = (p[168][0] + p[6][0]) / 2
    puente = filas(cx - 0.09 * e, p[168][1] - 0.06 * e, cx + 0.09 * e, p[6][1] + 0.06 * e)
    piel = []
    for ojo, boca in ((33, 61), (263, 291)):  # mejillas
        c = 0.45 * p[ojo] + 0.55 * p[boca]
        piel.append(filas(c[0] - 0.12 * e, c[1] - 0.12 * e, c[0] + 0.12 * e, c[1] + 0.12 * e))
    y_ceja, cxf = p[[105, 334, 66, 296]][:, 1].min(), (p[105][0] + p[334][0]) / 2
    piel.append(filas(cxf - 0.32 * e, y_ceja - 0.38 * e, cxf + 0.32 * e, y_ceja - 0.08 * e))  # frente
    niveles = [float(np.median(f)) for f in piel if f is not None]
    if puente is None or not niveles:
        return None
    return float(puente.max() / (np.median(niveles) + 1.0))  # la mediana: un flequillo o una barba no la mueven


class RevisionLentes:
    """Decide si hay lentes con los cuadros con cara de los últimos LENTES_REVISION_S segundos, no con uno solo."""

    def __init__(self, umbral: float = LENTES_UMBRAL, ventana_s: float = LENTES_REVISION_S):
        self.umbral, self.ventana_s = umbral, ventana_s
        self._marcas: deque[tuple[float, bool]] = deque()

    def agregar(self, t: float, puntaje: float | None):
        if puntaje is not None:
            self._marcas.append((t, puntaje >= self.umbral))
        while self._marcas and t - self._marcas[0][0] > self.ventana_s:
            self._marcas.popleft()

    def fraccion(self) -> float | None:
        """Fracción de cuadros con lentes, o None si aún no hay bastantes (10 cuadros que cubran el 70 % de la ventana)."""
        if len(self._marcas) < 10 or self._marcas[-1][0] - self._marcas[0][0] < 0.7 * self.ventana_s:
            return None
        return sum(m for _, m in self._marcas) / len(self._marcas)


def regiones(pts: np.ndarray, ancho: int, alto: int) -> list[tuple[int, int, int, int]]:
    """Frente y dos mejillas como rectángulos (x0, y0, x1, y1), a partir de puntos de la malla en píxeles: ahí se
    mide la luz de la cara.

    La escala es la distancia entre los rabillos externos de los ojos (puntos 33 y 263)."""
    escala = float(np.linalg.norm(pts[33] - pts[263]))
    if escala < 20:
        return []
    cejas = pts[[105, 334, 66, 296]]
    cx = (pts[105][0] + pts[334][0]) / 2
    y_ceja = cejas[:, 1].min()
    cajas = [(cx - 0.32 * escala, y_ceja - 0.38 * escala, cx + 0.32 * escala, y_ceja - 0.08 * escala)]  # frente
    for ojo, boca in ((33, 61), (263, 291)):  # mejillas: entre el rabillo del ojo y la comisura de la boca
        c = 0.45 * pts[ojo] + 0.55 * pts[boca]
        m = 0.12 * escala
        cajas.append((c[0] - m, c[1] - m, c[0] + m, c[1] + m))
    salida = []
    for x0, y0, x1, y1 in cajas:
        x0, y0 = max(0, int(x0)), max(0, int(y0))
        x1, y1 = min(ancho, int(x1)), min(alto, int(y1))
        if x1 - x0 >= 4 and y1 - y0 >= 4:
            salida.append((x0, y0, x1, y1))
    return salida


def color_piel(cuadro_bgr: np.ndarray, cajas) -> tuple[np.ndarray, float, float] | None:
    """(promedio RGB, brillo medio, fracción saturada) de los píxeles de las regiones."""
    zonas = [cuadro_bgr[y0:y1, x0:x1].reshape(-1, 3) for x0, y0, x1, y1 in cajas]
    if not zonas:
        return None
    px = np.concatenate(zonas).astype(np.float64)
    if len(px) == 0:
        return None
    rgb = px.mean(axis=0)[::-1]  # BGR -> RGB
    brillo = float(rgb @ np.array([0.299, 0.587, 0.114]))
    saturado = float((px.max(axis=1) >= 250).mean())
    return rgb, brillo, saturado


def cabeza_inclinada(t: np.ndarray, inclinacion) -> np.ndarray:
    """Cuadros con la cabeza inclinada más de INCLINACION_MAX grados respecto de los primeros 5 s (mirar abajo)."""
    t = np.asarray(t, float)
    if inclinacion is None:
        return np.zeros(len(t), bool)
    inc = np.asarray(inclinacion, float)
    validos = np.isfinite(inc)
    inicio = validos & (t - t[0] <= CALIBRACION_S)
    if inicio.sum() < 5:
        return np.zeros(len(t), bool)
    ref = float(np.median(inc[inicio]))
    return validos & (np.abs(inc - ref) > INCLINACION_MAX)


def analizar_ojos(t: np.ndarray, ears: np.ndarray, inclinacion=None) -> dict | None:
    """EAR por cuadro (NaN sin cara) -> ear_abierto, parpadeos, parpadeos_min y perclos.

    Si se da la inclinación de la cabeza, los cuadros con la cabeza muy inclinada (mirando hacia abajo) no cuentan:
    el párpado baja con la mirada y la cámara lo vería como un ojo cerrado."""
    t, ears = np.asarray(t, float), np.asarray(ears, float).copy()
    inclinada = cabeza_inclinada(t, inclinacion)
    ears[inclinada] = np.nan
    con_cara = np.isfinite(ears)
    if con_cara.sum() < 10:
        return None
    calibracion = ears[con_cara & (t - t[0] <= CALIBRACION_S)]
    abierto = float(np.median(calibracion if len(calibracion) >= 10 else ears[con_cara]))
    umbral_parpadeo, umbral_cerrado = PARPADEO_FRAC * abierto, CERRADO_FRAC * abierto
    parpadeos, seguidos = 0, 0
    for e in ears:  # un parpadeo = al menos 2 cuadros seguidos bajo el umbral; sin cara corta la racha
        if np.isfinite(e) and e < umbral_parpadeo:
            seguidos += 1
        else:
            parpadeos += seguidos >= PARPADEO_MIN_CUADROS
            seguidos = 0
    parpadeos += seguidos >= PARPADEO_MIN_CUADROS
    dt = np.diff(t, append=t[-1] + (np.median(np.diff(t)) if len(t) > 1 else 1 / FS))  # duración de cada cuadro
    tiempo_cara = float(dt[con_cara].sum())
    cerrado = float(dt[con_cara & (ears < umbral_cerrado)].sum())
    return {
        "ear_abierto": round(abierto, 3), "parpadeos": int(parpadeos),
        "parpadeos_min": round(parpadeos / (tiempo_cara / 60), 1) if tiempo_cara > 0 else None,
        "perclos": round(cerrado / tiempo_cara, 3) if tiempo_cara > 0 else None,
        "cabeza_inclinada_pct": round(float(inclinada.mean() * 100), 1),
    }


class Registro:
    """Lo que se juntó cuadro a cuadro durante una medición."""

    def __init__(self):
        self.t, self.ear, self.mar, self.brillo, self.saturado = [], [], [], [], []
        self.inclinacion, self.mano, self.mandibula, self.lentes = [], [], [], []
        self.ear_der, self.ear_izq = [], []  # cada ojo por separado (para no contar un guiño como parpadeo)
        self.con_lentes = False   # se midió con lentes porque no se los quitaron a tiempo
        self.sin_manos = False    # no se pudo usar la detección de manos
        self.camara = ""          # la que midió de verdad (CAMARA o, si no dio video, CAMARA_RESPALDO)
        self.aviso_camara = ""    # por qué se usó la de respaldo

    def agregar(self, t: float, pts, cuadro_bgr, inclinacion: float = float("nan"), mano: float = float("nan"),
                lentes: float | None = None, z=None):
        """mano: 1 con una mano en la boca, 0 sin, NaN si no se pudo ver. lentes: puntaje_lentes del cuadro.
        z: profundidad de cada punto (para medir la mandíbula en 3D)."""
        self.t.append(t)
        self.mano.append(mano)
        self.lentes.append(np.nan if lentes is None else lentes)
        if pts is None:
            self.ear.append(np.nan)
            self.ear_der.append(np.nan)
            self.ear_izq.append(np.nan)
            self.mar.append(np.nan)
            self.mandibula.append(np.nan)
            self.inclinacion.append(np.nan)
            return
        der, izq = ear_ojos(pts)
        self.ear.append((der + izq) / 2)  # el promedio: para los bostezos (los dos ojos se achican)
        self.ear_der.append(der)
        self.ear_izq.append(izq)
        self.mar.append(mar(pts))
        self.mandibula.append(mandibula(pts, z))
        self.inclinacion.append(inclinacion)
        piel = color_piel(cuadro_bgr, regiones(pts, cuadro_bgr.shape[1], cuadro_bgr.shape[0]))
        if piel is not None and mano != 1:  # con la mano en la boca, las mejillas pueden ser la mano: no cuenta
            self.brillo.append(piel[1])
            self.saturado.append(piel[2])

    def ears_parpadeo(self) -> np.ndarray:
        """EAR del ojo más abierto por cuadro (ver ear_parpadeo); si no hay de cada ojo, el promedio."""
        if len(self.ear_der) == len(self.ear_izq) == len(self.ear):
            return ear_parpadeo(self.ear_der, self.ear_izq)
        return np.asarray(self.ear, float)

    def resultado(self) -> dict:
        t = np.asarray(self.t, float)
        duracion = float(t[-1] - t[0]) if len(t) > 1 else 0.0
        cara_pct = float(np.isfinite(np.asarray(self.ear, float)).mean() * 100) if len(t) else 0.0
        fps = (len(t) - 1) / duracion if duracion > 0 else 0.0
        n = len(t)
        manos = self.mano if len(self.mano) == n and not self.sin_manos else None
        mand = self.mandibula if len(self.mandibula) == n else None
        boca = analizar_boca(t, np.asarray(self.mar, float), np.asarray(self.ear, float), manos, mand) if n > 1 else None
        ears = self.ears_parpadeo().copy()  # el ojo más abierto: un guiño no es parpadeo ni cierre
        if boca is not None:
            ears[boca["durante"]] = np.nan  # al bostezar se achican los ojos: no cuenta como parpadeo ni cierre
        incl = self.inclinacion if len(self.inclinacion) == len(t) else None
        ojos = analizar_ojos(t, ears, incl) if len(t) else None
        brillo = float(np.median(self.brillo)) if self.brillo else None
        saturado = float(np.mean(self.saturado)) if self.saturado else 0.0
        avisos = []
        if brillo is not None and brillo < LUZ_MIN:
            avisos.append("Poca luz en la cara: acerquen una lámpara de frente.")
        if (brillo is not None and brillo > LUZ_MAX) or saturado > SATURADO_MAX:
            avisos.append("Demasiada luz o reflejos en la cara.")
        if cara_pct < CARA_MIN_PCT:
            avisos.append(f"No se vio la cara el {100 - cara_pct:.0f} % del tiempo.")
        if fps < FPS_MIN:
            avisos.append(f"La cámara dio solo {fps:.0f} cuadros por segundo (mínimo {FPS_MIN}).")
        if ojos and ojos["cabeza_inclinada_pct"] > 20:
            avisos.append(f"La cabeza estuvo inclinada (mirando hacia abajo) el {ojos['cabeza_inclinada_pct']:.0f} % del "
                          f"tiempo: esos momentos no cuentan para los ojos.")
        if self.con_lentes:
            avisos.append("Se midió con lentes puestos: los ojos (parpadeos y PERCLOS) pueden salir mal y no cuentan "
                          "para el semáforo.")
        if self.sin_manos:
            avisos.append("No se pudo usar la detección de manos: los bostezos tapados con la mano no se cuentan.")
        if self.aviso_camara:
            avisos.append(self.aviso_camara)
        return {
            "camara": self.camara,
            "parpadeos_min": ojos["parpadeos_min"] if ojos else None,
            "parpadeos": ojos["parpadeos"] if ojos else None,
            "perclos": ojos["perclos"] if ojos else None,
            "ear_abierto": ojos["ear_abierto"] if ojos else None,
            "cabeza_inclinada_pct": ojos["cabeza_inclinada_pct"] if ojos else None,
            "bostezos": boca["bostezos"] if boca else None,
            "bostezos_min": boca["bostezos_min"] if boca else None,
            "bostezos_tapados": boca["bostezos_tapados"] if boca else None,
            "lentes": bool(self.con_lentes),
            "cara_detectada_pct": round(cara_pct, 1),
            "fps": round(fps, 1),
            "duracion_s": round(duracion, 1),
            "brillo_piel": round(brillo, 1) if brillo is not None else None,
            "avisos": avisos,
        }


# ================================================================ cámara y rostro
def fuente_camara(valor: str | None = None) -> str:
    return (valor or config.get("CAMARA", "0")).strip()


def es_usb(fuente: str) -> bool:
    """DroidCam por cable: con «adb forward» el celular se ve en esta laptop como 127.0.0.1."""
    return fuente.startswith(("http://127.0.0.1:", "http://localhost:"))


def buscar_adb() -> str | None:
    """adb de Android (ADB en config, el del PATH o el del SDK). El que trae el cliente de DroidCam va al final: dos adb
    de versiones distintas se cierran el servidor uno al otro."""
    import shutil
    opciones = [config.get("ADB", ""), shutil.which("adb") or "",
                os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
                r"C:\Program Files\DroidCam\Client\data\obs-plugins\droidcam-obs\adb\adb.exe"]
    return next((o for o in opciones if o and Path(o).is_file()), None)


def leer_dispositivos(salida: str) -> dict[str, str]:
    """Salida de «adb devices» -> {serie: estado} ("device" = listo, "unauthorized" = falta aceptar el permiso)."""
    return {s.strip(): e.strip() for s, e in (l.split("\t", 1) for l in salida.splitlines()[1:] if "\t" in l)}


def _correr_adb(adb: str, *args, timeout: float = 15):
    import subprocess
    return subprocess.run([adb, *args], capture_output=True, text=True, timeout=timeout,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _celular_listo(adb: str) -> tuple[str | None, str | None]:
    """(serie del celular listo, None) o (None, motivo para mostrar)."""
    dispositivos = leer_dispositivos(_correr_adb(adb, "devices").stdout)
    listos = [s for s, e in dispositivos.items() if e == "device"]
    if listos:
        return listos[0], None
    if "unauthorized" in dispositivos.values():
        return None, "El celular pide permiso: acepten «¿Permitir depuración USB?» en su pantalla."
    return None, "No veo el celular por USB: revisen el cable (que pase datos) y que la depuración USB esté activa."


def puente_usb(fuente: str) -> str | None:
    """Rehace «adb forward» hacia el puerto de DroidCam (se pierde cada vez que se desconecta el celular).
    None si quedó listo; si no, el motivo para mostrar."""
    import subprocess
    from urllib.parse import urlparse
    adb = buscar_adb()
    if adb is None:
        return "No encontré adb (Android SDK Platform-Tools) para usar DroidCam por cable."
    try:
        serie, motivo = _celular_listo(adb)
        if motivo:
            return motivo
        puerto = urlparse(fuente).port or 4747
        r = _correr_adb(adb, "-s", serie, "forward", f"tcp:{puerto}", f"tcp:{puerto}")
        if r.returncode != 0:
            return f"No se pudo conectar el puerto {puerto} por USB: {(r.stderr or r.stdout).strip()}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"adb falló: {e}"
    return None


def app_droidcam(salida_paquetes: str) -> str | None:
    """De «pm list packages com.dev47apps»: la app de DroidCam instalada (la normal antes que la de OBS), o None."""
    instaladas = {l.split(":", 1)[1].strip() for l in salida_paquetes.splitlines() if l.startswith("package:")}
    return next((a for a in DROIDCAM_APPS if a in instaladas), None)


def abrir_app_droidcam() -> str | None:
    """Con el celular por USB: enciende la pantalla y abre la app DroidCam (o la trae al frente si ya estaba abierta),
    y espera a que arranque. None si quedó abierta; si no, el motivo para mostrar."""
    import subprocess
    adb = buscar_adb()
    if adb is None:
        return "No encontré adb (Android SDK Platform-Tools) para usar DroidCam por cable."
    try:
        serie, motivo = _celular_listo(adb)
        if motivo:
            return motivo
        app = app_droidcam(_correr_adb(adb, "-s", serie, "shell", "pm", "list", "packages", "com.dev47apps").stdout)
        if app is None:
            return "El celular no tiene la app DroidCam instalada."
        print(f"[vision] DroidCam no da video: enciendo la pantalla del celular y abro {app}...")
        _correr_adb(adb, "-s", serie, "shell", "input", "keyevent", "KEYCODE_WAKEUP")
        _correr_adb(adb, "-s", serie, "shell", "monkey", "-p", app, "-c", "android.intent.category.LAUNCHER", "1")
        fin = time.time() + DROIDCAM_ESPERA_S
        while time.time() < fin:
            if _correr_adb(adb, "-s", serie, "shell", "pidof", app).stdout.strip():
                return None  # abierta: abrir_celular sigue probando hasta que dé video
            time.sleep(0.5)
    except (OSError, subprocess.SubprocessError) as e:
        return f"adb falló: {e}"
    return "No se pudo abrir DroidCam en el celular: desbloquéenlo y ábranla."


def abrir_directa(fuente: str):
    """(cap, primer cuadro con imagen, None) o (None, None, motivo). Índice de cámara o URL."""
    cap = abrir_camara(fuente)
    if cap is None:
        if es_usb(fuente):
            extra = (" Abran la app DroidCam en el celular y déjenla en pantalla, y cierren DroidCam en la laptop: el "
                     "celular acepta un programa a la vez.")
        elif not fuente.isdigit():
            extra = (" ¿DroidCam está tomado por otro programa (por ejemplo, el cliente de Windows)? El celular acepta "
                     "uno a la vez.")
        else:
            extra = " ¿Está ocupada o desconectada?"
        return None, None, f"No se pudo abrir la cámara {fuente}.{extra}"
    cuadro = primer_cuadro(cap)
    if cuadro is None or es_plano(cuadro):
        cap.release()
        if cuadro is None:
            return None, None, f"La cámara {fuente} no entrega imágenes."
        return None, None, (f"La cámara {fuente} entrega una imagen plana, sin video (si es la cámara virtual de "
                            f"DroidCam, usen la URL del celular en CAMARA).")
    return cap, cuadro, None


def abrir_celular(fuente: str):
    """DroidCam por cable: rehace «adb forward» y prueba; si no da video, enciende la pantalla, abre la app y vuelve a
    probar. (cap, cuadro, None) o (None, None, motivo)."""
    motivo = puente_usb(fuente)
    if motivo:
        return None, None, motivo
    cap, cuadro, motivo = abrir_directa(fuente)
    if cap is not None:
        return cap, cuadro, None
    motivo_app = abrir_app_droidcam()
    if motivo_app:
        return None, None, motivo_app
    fin = time.time() + DROIDCAM_ESPERA_S  # al volver al frente, DroidCam tarda unos segundos en dar video
    while time.time() < fin:
        cap, cuadro, _ = abrir_directa(fuente)
        if cap is not None:
            return cap, cuadro, None
        time.sleep(1.0)
    return None, None, ("El celular está conectado pero DroidCam no da video: desbloquéenlo, dejen la app DroidCam "
                        "abierta en pantalla y cierren DroidCam en la laptop.")


def abrir_con_respaldo(fuente: str, al_buscar=None, respaldo: str | None = None):
    """Busca la cámara: primero `fuente` (CAMARA; si es el celular por cable, también intenta abrir la app) y, si no
    da video, la de la laptop (CAMARA_RESPALDO). (cap, fuente usada, primer cuadro, aviso); el aviso dice por qué se
    usó la de respaldo ("" si no hizo falta). Sin ninguna, ErrorMedicion con el motivo."""
    respaldo = CAMARA_RESPALDO if respaldo is None else respaldo
    if al_buscar:
        al_buscar("Buscando la cámara del celular…" if es_usb(fuente) else f"Abriendo la cámara {fuente}…")
    cap, cuadro, motivo = abrir_celular(fuente) if es_usb(fuente) else abrir_directa(fuente)
    if cap is not None:
        return cap, fuente, cuadro, ""
    if not respaldo or respaldo == fuente:
        raise ErrorMedicion(motivo)
    print(f"[vision] {motivo} Pruebo la cámara de la laptop ({respaldo}).")
    if al_buscar:
        al_buscar("No responde el celular: usando la cámara de la laptop…")
    cap, cuadro, motivo_respaldo = abrir_directa(respaldo)
    if cap is None:
        raise ErrorMedicion(f"{motivo} Tampoco respondió la cámara de la laptop: {motivo_respaldo}")
    return cap, respaldo, cuadro, f"Se midió con la cámara de la laptop porque no respondió el celular: {motivo}"


def abrir_camara(fuente: str):
    """Media Foundation primero: en Windows da 30 cuadros por segundo donde DirectShow da 16, y ve las cámaras
    virtuales nuevas (como DroidCam). Si no abre, DirectShow."""
    import cv2
    if not fuente.isdigit():
        cap = cv2.VideoCapture(fuente)  # URL de DroidCam u otra cámara por red
        return cap if cap.isOpened() else None
    for api in (cv2.CAP_MSMF, cv2.CAP_DSHOW):
        cap = cv2.VideoCapture(int(fuente), api)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            return cap
        cap.release()
    return None


def es_plano(cuadro) -> bool:
    """Imagen sin variación dentro de cada canal: negro, gris o el verde liso de una cámara virtual sin video."""
    return float(cuadro.reshape(-1, cuadro.shape[-1]).std(axis=0).max()) < 2


def primer_cuadro(cap, segundos: float = 4.0):
    """Primer cuadro con imagen de verdad (las cámaras virtuales tardan y empiezan en negro), o None."""
    inicio, cuadro = time.time(), None
    while time.time() - inicio < segundos:
        ok, c = cap.read()
        if ok and c is not None:
            cuadro = c
            if not es_plano(c):
                return c
        time.sleep(0.03)
    return cuadro  # plano (o None si nunca llegó nada)


class Camara:
    """Lee la cámara en un hilo aparte y entrega siempre el cuadro más nuevo con la hora en que llegó.

    Así las horas son exactas aunque procesar un cuadro tarde más que capturarlo, y no se acumula retraso
    (importa con DroidCam por Wi-Fi). Si el proceso va más lento que la cámara, se saltan cuadros."""

    def __init__(self, cap):
        self.cap = cap
        self._cuadro, self._t, self._n, self._entregado = None, 0.0, 0, 0
        self._cond = threading.Condition()
        self._vivo = True
        self._hilo = threading.Thread(target=self._leer, daemon=True)
        self._hilo.start()

    def _leer(self):
        while self._vivo:
            ok, c = self.cap.read()
            t = time.perf_counter()
            if ok and c is not None:
                with self._cond:
                    self._cuadro, self._t, self._n = c, t, self._n + 1
                    self._cond.notify_all()
            else:
                time.sleep(0.01)

    def siguiente(self, espera: float = 3.0):
        """(cuadro, hora) nuevo, o (None, None) si no llega nada en `espera` segundos."""
        with self._cond:
            fin = time.perf_counter() + espera
            while self._n == self._entregado:
                restante = fin - time.perf_counter()
                if restante <= 0:
                    return None, None
                self._cond.wait(restante)
            self._entregado = self._n
            return self._cuadro, self._t

    def cerrar(self):
        self._vivo = False
        self._hilo.join(timeout=2)
        self.cap.release()


def listar_camaras():
    import cv2
    print("Probando cámaras del 0 al 5 (la luz de la cámara puede encenderse un momento)...")
    hay = False
    for i in range(6):
        cap = abrir_camara(str(i))
        if cap is None:
            continue
        cuadro = primer_cuadro(cap)
        if cuadro is not None:
            hay = True
            n, t0 = 0, time.time()
            while time.time() - t0 < 1.5:
                n += cap.read()[0]
            nota = "  <- imagen plana, sin video (cámara virtual sin transmitir)" if es_plano(cuadro) else ""
            print(f"   {i}: {cuadro.shape[1]} x {cuadro.shape[0]}, ~{n / 1.5:.0f} cuadros por segundo{nota}")
        cap.release()
    if not hay:
        print("   No encontré cámaras.")
    print("\nPongan el número en CAMARA dentro de config.env, o la URL de DroidCam (http://IP:4747/video).")


def asegurar_modelo(ruta: Path = MODELO, url: str = URL_MODELO, que: str = "de la cara") -> Path:
    if ruta.exists():
        return ruta
    import urllib.request
    print(f"[vision] Descargando el modelo {que} a {ruta} (una sola vez)...")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    parcial = ruta.with_suffix(".parcial")
    try:
        urllib.request.urlretrieve(url, parcial)
        parcial.replace(ruta)  # si se corta la descarga no queda un modelo a medias
    except OSError as e:
        raise ErrorMedicion(f"Falta {ruta.name} y no se pudo descargar ({e}). Corran instalar.bat.") from e
    return ruta


class Rostro:
    """FaceLandmarker de MediaPipe Tasks en modo video: cuadro BGR -> 478 puntos en píxeles, o None."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision as mpv
        self._mp = mp
        opciones = mpv.FaceLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(asegurar_modelo())),
                                             running_mode=mpv.RunningMode.VIDEO, num_faces=1,
                                             output_facial_transformation_matrixes=True)  # para la inclinación
        self._lm = mpv.FaceLandmarker.create_from_options(opciones)
        self.conexiones = np.array([(c.start, c.end) for c in mpv.FaceLandmarksConnections.FACE_LANDMARKS_TESSELATION])
        self._ultimo_ms = -1
        self.inclinacion = float("nan")  # grados de cabeceo (arriba/abajo) del último cuadro con cara
        self.z = None                    # profundidad de cada punto del último cuadro con cara (escala de x, píxeles)

    def puntos(self, cuadro_bgr, t_s: float):
        import cv2
        ms = max(int(t_s * 1000), self._ultimo_ms + 1)  # el modo video exige horas crecientes
        self._ultimo_ms = ms
        rgb = cv2.cvtColor(cuadro_bgr, cv2.COLOR_BGR2RGB)
        r = self._lm.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ms)
        if not r.face_landmarks:
            self.inclinacion, self.z = float("nan"), None
            return None
        self.inclinacion = float("nan")
        self.z = np.array([p.z * cuadro_bgr.shape[1] for p in r.face_landmarks[0]])  # profundidad, en escala de x
        if getattr(r, "facial_transformation_matrixes", None):
            rot = np.asarray(r.facial_transformation_matrixes[0], float)[:3, :3]
            self.inclinacion = float(np.degrees(np.arctan2(rot[2, 1], rot[2, 2])))  # giro sobre el eje horizontal
        h, w = cuadro_bgr.shape[:2]
        return np.array([(p.x * w, p.y * h) for p in r.face_landmarks[0]])

    def cerrar(self):
        self._lm.close()


class Manos:
    """HandLandmarker de MediaPipe Tasks en modo video: cuadro BGR -> lista de manos (21 puntos en píxeles cada una).
    Recibe el cuadro a la mitad de tamaño: una mano junto a la cara se ve grande y así tarda menos."""

    def __init__(self):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python import vision as mpv
        self._mp = mp
        modelo = asegurar_modelo(MODELO_MANOS, URL_MODELO_MANOS, "de las manos")
        opciones = mpv.HandLandmarkerOptions(base_options=BaseOptions(model_asset_path=str(modelo)),
                                             running_mode=mpv.RunningMode.VIDEO, num_hands=2,
                                             min_hand_detection_confidence=0.4, min_hand_presence_confidence=0.4,
                                             min_tracking_confidence=0.4)
        self._lm = mpv.HandLandmarker.create_from_options(opciones)
        self.conexiones = [(c.start, c.end) for c in mpv.HandLandmarksConnections.HAND_CONNECTIONS]
        self._ultimo_ms = -1

    @classmethod
    def crear(cls):
        """Manos, o None si no se puede (sin el modelo y sin internet): se mide igual, sin los bostezos tapados."""
        try:
            return cls()
        except Exception as e:  # noqa: BLE001 - cualquier falla de MediaPipe o de la descarga
            print(f"[vision] Sin detección de manos ({e}): los bostezos tapados con la mano no se van a contar.")
            return None

    def puntos(self, cuadro_bgr, t_s: float) -> list[np.ndarray]:
        import cv2
        ms = max(int(t_s * 1000), self._ultimo_ms + 1)  # el modo video exige horas crecientes
        self._ultimo_ms = ms
        h, w = cuadro_bgr.shape[:2]
        chico = cv2.cvtColor(cv2.resize(cuadro_bgr, (w // 2, h // 2), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2RGB)
        r = self._lm.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=chico), ms)
        return [np.array([(p.x * w, p.y * h) for p in mano]) for mano in (r.hand_landmarks or [])]

    def cerrar(self):
        self._lm.close()


# ================================================================ velocidad
# Los cuadros se procesan a este ancho como mucho: DroidCam manda 1280 x 720 y procesarlos así bajaba a ~13 cuadros
# por segundo. EAR, MAR y el puntaje de lentes son proporciones: no cambian con el tamaño (la cara sigue pasando de
# los 40 px entre ojos que pide puntaje_lentes).
PROCESO_ANCHO = 640


def achicar(cuadro, ancho: int = PROCESO_ANCHO):
    import cv2
    h, w = cuadro.shape[:2]
    if w <= ancho:
        return cuadro
    return cv2.resize(cuadro, (ancho, max(1, round(h * ancho / w))), interpolation=cv2.INTER_AREA)


def sin_modo_eficiencia():
    """Windows 11 manda los procesos en segundo plano a los núcleos de eficiencia (EcoQoS). Durante la prueba de
    reacción el navegador tiene el foco y la cámara bajaba de ~27 a ~13 cuadros por segundo (en esta laptop, el mismo
    cálculo tarda 5 a 7 veces más con EcoQoS). Se pide velocidad completa para este proceso. En otro sistema, nada."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    class Estado(ctypes.Structure):  # PROCESS_POWER_THROTTLING_STATE
        _fields_ = [("Version", wintypes.ULONG), ("ControlMask", wintypes.ULONG), ("StateMask", wintypes.ULONG)]
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.SetProcessInformation.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        k32.SetProcessInformation.restype = wintypes.BOOL
        estado = Estado(1, 0x1, 0x0)  # EXECUTION_SPEED en el control y apagado en el estado = sin EcoQoS
        if not k32.SetProcessInformation(k32.GetCurrentProcess(), 4, ctypes.byref(estado), ctypes.sizeof(estado)):
            print(f"[vision] No pude quitar el modo eficiencia de Windows (error {ctypes.get_last_error()}).")
    except (OSError, AttributeError) as e:  # Windows viejo sin SetProcessInformation
        print(f"[vision] No pude quitar el modo eficiencia de Windows: {e}")


# ================================================================ video en vivo para la estación
VIDEO_PUERTO = config.get_int("VISION_VIDEO_PUERTO", 8091)  # http://127.0.0.1:8091/video (solo en esta laptop)
VIDEO_ANCHO = PROCESO_ANCHO  # el panel de dibujar() (EAR, parpadeos, bostezos) está pensado para 640 px
VIDEO_CADA_S = 0.125     # como mucho 8 cuadros por segundo


def cuadro_web(cuadro, pts, conexiones, info: dict | None = None, ancho: int = VIDEO_ANCHO) -> bytes | None:
    """JPEG del cuadro (ya en espejo) para la estación: con `info`, lo mismo que la ventana de visión (malla y el
    conteo en vivo de parpadeos y bostezos, el EAR y el tiempo); sin `info`, solo la malla. No toca `cuadro`."""
    import cv2
    h, w = cuadro.shape[:2]
    f = min(1.0, ancho / w)
    img = cuadro.copy() if f == 1.0 else cv2.resize(cuadro, (ancho, max(1, round(h * f))), interpolation=cv2.INTER_AREA)
    p = None if pts is None else np.asarray(pts, float)[:, :2] * f
    if info is not None:
        info = dict(info)
        if f != 1.0 and info.get("manos"):
            info["manos"] = [np.asarray(m, float) * f for m in info["manos"]]
        dibujar(img, p, conexiones, info)
    elif p is not None:
        cv2.polylines(img, p[conexiones].astype(np.int32), False, (200, 170, 90), 1, cv2.LINE_AA)
        for i in OJO_DER + OJO_IZQ:
            cv2.circle(img, tuple(p[i].astype(int)), 2, (40, 210, 255), -1, cv2.LINE_AA)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 70])
    return jpg.tobytes() if ok else None


class Transmision:
    """Video MJPEG para el panel de la cámara de la estación (http://127.0.0.1:VIDEO_PUERTO/video): el último cuadro
    con la malla, mientras se mide. Solo escucha en 127.0.0.1: el video de la cara no sale de esta laptop."""

    def __init__(self):
        self.activa = False
        self._jpg, self._n, self._ultimo = None, 0, 0.0
        self._cond = threading.Condition()

    def toca(self) -> bool:
        """¿Ya pasó VIDEO_CADA_S desde el último cuadro? (si no, ni se arma lo que se dibuja)."""
        return self.activa and time.perf_counter() - self._ultimo >= VIDEO_CADA_S

    def poner(self, cuadro, pts, conexiones, info: dict | None = None):
        """Agrega un cuadro si toca (si no, no gasta tiempo en el JPEG). No modifica `cuadro`."""
        if not self.toca():
            return
        self._ultimo = time.perf_counter()
        jpg = cuadro_web(cuadro, pts, conexiones, info)
        if jpg:
            with self._cond:
                self._jpg, self._n = jpg, self._n + 1
                self._cond.notify_all()

    def limpiar(self):
        """Al empezar otra medición: que la estación no muestre el último cuadro de la anterior."""
        with self._cond:
            self._jpg = None

    def esperar(self, visto: int, espera: float = 1.0) -> tuple[int, bytes | None]:
        """(número, JPEG) del cuadro siguiente a `visto`, o el mismo si no llega otro en `espera` segundos."""
        with self._cond:
            if self._n == visto or self._jpg is None:  # sin cuadro todavía: también se espera (si no, gira sin parar)
                self._cond.wait(espera)
            return self._n, self._jpg

    def arrancar(self, puerto: int = VIDEO_PUERTO) -> bool:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        transmision = self

        class Manejador(BaseHTTPRequestHandler):
            def log_message(self, *args):  # sin una línea por pedido en la consola
                pass

            def do_GET(self):
                if self.path.split("?")[0] != "/video":
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=cuadro")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                visto, quieto = -1, 0
                try:
                    while True:
                        n, jpg = transmision.esperar(visto)
                        if jpg is None:
                            continue
                        if n == visto:  # sin cuadros nuevos (no se está midiendo): cada ~2 s se reenvía el último,
                            quieto += 1  # así se nota si la estación ya cerró el panel y el hilo termina
                            if quieto < 2:
                                continue
                        visto, quieto = n, 0
                        self.wfile.write(b"--cuadro\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                         + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionError, OSError):
                    return  # la estación cerró el panel o se recargó

        try:
            servidor = ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
        except OSError as e:
            print(f"[vision] No pude abrir el video en vivo en el puerto {puerto}: {e}")
            return False
        servidor.daemon_threads = True
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.activa = True
        print(f"[vision] Video en vivo para la estación: http://127.0.0.1:{puerto}/video")
        return True


TRANSMISION = Transmision()


# ================================================================ vista previa
def dibujar(cuadro, pts, conexiones, info: dict):
    """Malla, zonas de luz, ojos y un panel con la cara, el EAR y el tiempo (texto sin tildes: OpenCV)."""
    import cv2
    capa = cuadro.copy()
    if pts is not None:
        segmentos = pts[conexiones].astype(np.int32)
        cv2.polylines(capa, segmentos, False, (200, 170, 90), 1, cv2.LINE_AA)
        for x0, y0, x1, y1 in regiones(pts, cuadro.shape[1], cuadro.shape[0]):
            cv2.rectangle(capa, (x0, y0), (x1, y1), (80, 220, 80), 2)
        for i in OJO_DER + OJO_IZQ:
            cv2.circle(capa, tuple(pts[i].astype(int)), 2, (40, 210, 255), -1, cv2.LINE_AA)
        if info.get("mano"):  # la zona de la boca, en amarillo, cuando una mano la tapa
            x0, y0, x1, y1 = (int(v) for v in zona_boca(pts))
            cv2.rectangle(capa, (x0, y0), (x1, y1), (60, 200, 255), 2)
    for mano in info.get("manos") or []:
        for a, b in info.get("conexiones_mano") or []:
            cv2.line(capa, tuple(mano[a].astype(int)), tuple(mano[b].astype(int)), (255, 190, 80), 2, cv2.LINE_AA)
    cuadro[:] = cv2.addWeighted(capa, 0.75, cuadro, 0.25, 0)
    h, w = cuadro.shape[:2]
    panel = cuadro.copy()
    cv2.rectangle(panel, (0, 0), (w, 118), (12, 16, 22), -1)
    cuadro[:118] = cv2.addWeighted(panel[:118], 0.78, cuadro[:118], 0.22, 0)
    blanco, gris, verde, amarillo = (240, 240, 240), (170, 170, 170), (110, 220, 110), (60, 200, 255)
    cv2.putText(cuadro, "APTO HOY  -  VISION", (14, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, gris, 1, cv2.LINE_AA)
    puntaje, fraccion = info.get("lentes") or (None, None)
    if puntaje is not None:  # para ajustar LENTES_UMBRAL mirando el número con y sin lentes
        decision = "?" if fraccion is None else ("SI" if fraccion >= LENTES_FRAC else "NO")
        texto = f"LENTES {decision}   puntaje {puntaje:.1f} (umbral {LENTES_UMBRAL:g})"
        (tw, _), _ = cv2.getTextSize(texto, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(cuadro, texto, (w - tw - 14, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.5, gris, 1, cv2.LINE_AA)
    texto, color = ("NO SE VE LA CARA", amarillo) if pts is None else ("CARA DETECTADA", verde)
    cv2.putText(cuadro, texto, (14, 60), cv2.FONT_HERSHEY_DUPLEX, 0.85, color, 1, cv2.LINE_AA)
    e = info.get("ear")
    ojos = f"EAR  {e:.2f}" if e is not None and np.isfinite(e) else "EAR  -"
    if info.get("parpadeos") is not None:
        ojos += f"     PARPADEOS  {info['parpadeos']}"
    if info.get("bostezos") is not None:
        ojos += f"     BOSTEZOS  {info['bostezos']}"
    cv2.putText(cuadro, ojos, (14, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.65, blanco, 1, cv2.LINE_AA)
    if info.get("mano"):
        cv2.putText(cuadro, "MANO EN LA BOCA", (w - 260, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6, amarillo, 2, cv2.LINE_AA)
    elif info.get("boca_abierta"):
        cv2.putText(cuadro, "BOCA MUY ABIERTA (posible bostezo)", (w - 430, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    amarillo, 2, cv2.LINE_AA)
    if info.get("diagnostico"):  # la última mano en la boca: qué se midió (en --ver, para ajustar)
        franja = cuadro.copy()
        cv2.rectangle(franja, (0, 118), (w, 148), (12, 16, 22), -1)
        cuadro[118:148] = cv2.addWeighted(franja[118:148], 0.78, cuadro[118:148], 0.22, 0)
        cv2.putText(cuadro, info["diagnostico"], (14, 138), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    verde if info["diagnostico"].endswith("BOSTEZO") else amarillo, 1, cv2.LINE_AA)
    derecha = f"QUEDAN {info['quedan']:.0f} s" if info.get("quedan") is not None else "VISTA PREVIA  (q para salir)"
    (tw, _), _ = cv2.getTextSize(derecha, cv2.FONT_HERSHEY_DUPLEX, 0.75, 1)
    cv2.putText(cuadro, derecha, (w - tw - 14, 60), cv2.FONT_HERSHEY_DUPLEX, 0.75, blanco, 1, cv2.LINE_AA)
    for i, aviso in enumerate(info.get("avisos", [])):
        cv2.putText(cuadro, aviso, (14, h - 18 - 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, amarillo, 2, cv2.LINE_AA)
    if info.get("progreso") is not None:
        cv2.rectangle(cuadro, (0, h - 6), (int(w * info["progreso"]), h), (90, 200, 255), -1)
    lineas = info.get("mensaje") or []
    if lineas:  # aviso grande en el centro (p. ej. «quítate los lentes»)
        escalas = [1.1] + [0.75] * (len(lineas) - 1)
        tamanos = [cv2.getTextSize(x, cv2.FONT_HERSHEY_DUPLEX, s, 2)[0] for x, s in zip(lineas, escalas)]
        ancho = max(tw for tw, _ in tamanos) + 60
        alto = sum(th for _, th in tamanos) + 26 * len(lineas) + 30
        x0, y0 = (w - ancho) // 2, (h - alto) // 2
        fondo = cuadro.copy()
        cv2.rectangle(fondo, (x0, y0), (x0 + ancho, y0 + alto), (12, 16, 22), -1)
        cuadro[:] = cv2.addWeighted(fondo, 0.85, cuadro, 0.15, 0)
        cv2.rectangle(cuadro, (x0, y0), (x0 + ancho, y0 + alto), amarillo, 2)
        y = y0 + 22
        for texto, s, (tw, th) in zip(lineas, escalas, tamanos):
            y += th + 18
            cv2.putText(cuadro, texto, ((w - tw) // 2, y), cv2.FONT_HERSHEY_DUPLEX, s,
                        amarillo if s > 1 else blanco, 2 if s > 1 else 1, cv2.LINE_AA)
    return cuadro


def avisos_en_vivo(registro: Registro) -> list[str]:
    """Avisos cortos (ASCII) para la ventana, con los últimos 2 s."""
    if not registro.brillo:
        return []
    brillo = float(np.median(registro.brillo[-60:]))
    if brillo < LUZ_MIN:
        return ["POCA LUZ: acerquen una lampara de frente"]
    if brillo > LUZ_MAX or np.mean(registro.saturado[-60:]) > SATURADO_MAX:
        return ["DEMASIADA LUZ O REFLEJOS"]
    return []


def capturar(segundos: float | None, ventana: bool = True, al_avanzar=None, camara: str | None = None,
             revisar_lentes: bool = False, al_lentes=None, al_buscar=None) -> Registro:
    """Abre la cámara y junta cuadros durante `segundos` (None = hasta q/Esc). al_avanzar(quedan) cada 5 s.

    La cámara la busca abrir_con_respaldo (el celular y, si no da video, la de la laptop); al_buscar(mensaje) avisa
    mientras busca. Con revisar_lentes (y `segundos`), antes de empezar mira LENTES_REVISION_S si hay lentes; si hay,
    llama a al_lentes() y espera a que se los quiten (o LENTES_ESPERA_S) antes de empezar a contar los `segundos`."""
    import cv2
    TRANSMISION.limpiar()
    cap, fuente, _, aviso_camara = abrir_con_respaldo(fuente_camara(camara), al_buscar)
    print(f"[vision] Cámara: {fuente}" + (f" ({aviso_camara})" if aviso_camara else ""))
    rostro = Rostro()
    manos = Manos.crear()
    registro = Registro()
    registro.sin_manos = manos is None
    registro.camara, registro.aviso_camara = fuente, aviso_camara
    cam = None
    try:
        for _ in range(10):  # que se ajuste la exposición
            cap.read()
        cam = Camara(cap)
        if ventana:
            cv2.namedWindow(VENTANA, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(VENTANA, 960, 720)
            try:
                cv2.setWindowProperty(VENTANA, cv2.WND_PROP_TOPMOST, 1)  # que quede adelante
            except cv2.error:
                pass
        t0 = time.perf_counter()  # hora de los modelos (siempre creciente)
        inicio = t0               # desde aquí cuentan los `segundos`; se mueve al terminar la revisión de lentes
        fase = "revisando" if revisar_lentes and segundos is not None else "midiendo"
        revision, espera_desde = RevisionLentes(), 0.0
        ultimo_aviso, ultimo_vivo, parpadeos, bostezos = -5.0, 0.0, None, None
        n, manos_vistas, zona, zona_t = 0, [], None, -9.0
        explicados, ultimo_episodio = set(), None  # manos en la boca ya explicadas en la consola
        bocas_explicadas: set = set()               # aperturas de boca a la vista ya explicadas (explicar_bostezos)
        while True:
            cuadro, llegada = cam.siguiente()
            if cuadro is None:
                raise ErrorMedicion("La cámara dejó de enviar imágenes.")
            ahora = llegada - t0  # la hora en que llegó el cuadro, no la de procesarlo
            cuadro = cv2.flip(achicar(cuadro), 1)  # a PROCESO_ANCHO y como un espejo
            pts = rostro.puntos(cuadro, ahora)
            if pts is not None:
                zona, zona_t = zona_boca(pts), ahora
            if manos is not None and n % MANOS_CADA == 0:
                manos_vistas = manos.puntos(cuadro, ahora)
            n += 1
            # Si la mano tapa tanto que se pierde la cara, vale la última zona de la boca (de hace 0,5 s o menos).
            mano = (float(mano_en_boca(zona, manos_vistas)) if manos is not None and zona is not None
                    and ahora - zona_t <= 0.5 else float("nan"))
            p_lentes = puntaje_lentes(cuadro, pts) if pts is not None else None
            revision.agregar(ahora, p_lentes)
            fraccion = revision.fraccion()

            if fase == "revisando":
                if fraccion is not None and fraccion >= LENTES_FRAC:
                    fase, espera_desde = "lentes", ahora
                    print("[vision] Se ven lentes: se pide quitarlos antes de medir.")
                    if al_lentes:
                        al_lentes()
                elif fraccion is not None or ahora > LENTES_REVISION_S + 6:  # sin lentes (o aún no se ve la cara)
                    fase, inicio, ultimo_aviso = "midiendo", llegada, -5.0
            elif fase == "lentes":
                if fraccion is not None and fraccion <= LENTES_LIBRE_FRAC:
                    print("[vision] Ya no se ven lentes: empieza la medición.")
                    fase, inicio, ultimo_aviso = "midiendo", llegada, -5.0
                elif ahora - espera_desde >= LENTES_ESPERA_S:
                    print(f"[vision] Siguen los lentes a los {LENTES_ESPERA_S:.0f} s: se mide igual (los ojos no cuentan).")
                    registro.con_lentes = True
                    fase, inicio, ultimo_aviso = "midiendo", llegada, -5.0

            midiendo = fase == "midiendo"
            t = llegada - inicio
            quedan = None
            if midiendo:
                registro.agregar(t, pts, cuadro, rostro.inclinacion, mano, p_lentes, rostro.z)
                quedan = None if segundos is None else max(0.0, segundos - t)
                if al_avanzar and quedan is not None and t - ultimo_aviso >= 5:
                    ultimo_aviso = t
                    al_avanzar(quedan)
            # El conteo en vivo (y lo que se dibuja) también hace falta sin ventana si la estación mira el video
            if ventana or TRANSMISION.activa:
                if midiendo and t - ultimo_vivo >= 1.0:  # los parpadeos y los bostezos, una vez por segundo
                    ultimo_vivo = t
                    tr = np.asarray(registro.t)
                    if t > CALIBRACION_S:  # también en --ver
                        ojos = analizar_ojos(tr, registro.ears_parpadeo(), registro.inclinacion)
                        parpadeos = ojos["parpadeos"] if ojos else None
                    if len(tr) > 1:
                        bostezos = analizar_boca(tr, np.asarray(registro.mar), np.asarray(registro.ear),
                                                 None if manos is None else registro.mano, registro.mandibula)["bostezos"]
                        if manos is not None:  # cuando la mano ya se fue, se explica qué se midió y qué faltó
                            for ep in episodios_mano(tr, registro.mar, registro.ear, registro.mano, registro.mandibula):
                                clave = round(ep["mano_desde"], 2)
                                if ep["fin"] < t - 0.6 and clave not in explicados and not ep["pendiente"]:
                                    explicados.add(clave)
                                    ultimo_episodio = ep
                                    print(texto_episodio(ep))
                        for linea in explicar_bostezos(registro, bocas_explicadas, t - 0.6, manos is not None):
                            print(linea)
            if ventana or TRANSMISION.toca():  # sin ventana, solo cuando toca un cuadro del video (8 por segundo)
                mensaje = None
                if fase == "lentes":
                    mensaje = ["SE VEN LENTES", "Quitatelos para continuar con la medicion",
                               f"(si no, se mide igual en {max(0.0, LENTES_ESPERA_S - (ahora - espera_desde)):.0f} s)"]
                elif fase == "revisando":
                    mensaje = ["PREPARANDO...", "Mira a la camara"]
                mar_ahora = mar(pts) if pts is not None else float("nan")
                info = {"ear": ear_cara(pts) if pts is not None else None,
                        "parpadeos": parpadeos, "quedan": quedan, "bostezos": bostezos,
                        "boca_abierta": np.isfinite(mar_ahora) and mar_ahora >= BOSTEZO_MAR, "mano": mano == 1,
                        "manos": manos_vistas, "conexiones_mano": manos.conexiones if manos else None,
                        "lentes": (p_lentes, fraccion), "mensaje": mensaje,
                        "diagnostico": texto_episodio(ultimo_episodio, corto=True)
                        if ultimo_episodio and segundos is None else None,  # solo en --ver
                        "progreso": None if segundos is None or not midiendo else min(1.0, t / segundos),
                        "avisos": avisos_en_vivo(registro) if midiendo else []}
                TRANSMISION.poner(cuadro, pts, rostro.conexiones, info)  # sobre una copia: antes de dibujar()
            if ventana:
                cv2.imshow(VENTANA, dibujar(cuadro, pts, rostro.conexiones, info))
                tecla = cv2.waitKey(1) & 0xFF
                if tecla in (ord("q"), 27):
                    if segundos is None:
                        break
                    raise ErrorMedicion("Medición cancelada desde la ventana.")
                if cv2.getWindowProperty(VENTANA, cv2.WND_PROP_VISIBLE) < 1:  # cerraron la ventana con la X
                    if segundos is None:
                        break
                    raise ErrorMedicion("Se cerró la ventana de la cámara.")
            if quedan is not None and quedan <= 0:
                break
        for linea in explicar_bostezos(registro, bocas_explicadas, float("inf"), manos is not None):
            print(linea)  # las que faltaban (y todas, si se midió sin ventana)
    finally:
        if cam is not None:
            cam.cerrar()
        else:
            cap.release()
        rostro.cerrar()
        if manos is not None:
            manos.cerrar()
        if ventana:
            cv2.destroyWindow(VENTANA)
            cv2.waitKey(1)
    return registro


# ================================================================ flujo completo
def guardar_historial(mensaje: dict):
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps(mensaje, ensure_ascii=False) + "\n")


def guardar_trazas(registro: Registro, sesion: str):
    """Series numéricas de la medición (sin imágenes): hora, EAR, MAR, mano en la boca, mandíbula y
    puntaje de lentes por cuadro, para validar y ajustar los umbrales después. datos/vision/trazas/{sesion}.npz"""
    carpeta = CARPETA_DATOS / "trazas"
    carpeta.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(carpeta / f"{sesion}.npz", t=np.asarray(registro.t),
                        ear=np.asarray(registro.ear, float), ear_der=np.asarray(registro.ear_der, float),
                        ear_izq=np.asarray(registro.ear_izq, float), mar=np.asarray(registro.mar, float),
                        inclinacion=np.asarray(registro.inclinacion, float), mano=np.asarray(registro.mano, float),
                        mandibula=np.asarray(registro.mandibula, float), lentes=np.asarray(registro.lentes, float))


def evaluar(persona: str, segundos: float, linea_base: bool, cli: ClienteMQTT | None, sesion: str = "",
            ventana: bool = True, camara: str | None = None) -> dict | None:
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    sesion = sesion or marca

    def estado(**datos):
        if cli:
            cli.publicar("apto/control/estado_vision", {"persona": persona, "sesion": sesion, **datos})

    print(f"[vision] Midiendo a {persona} durante {segundos:.0f} s...")
    try:
        registro = capturar(segundos, ventana, lambda q: estado(estado="midiendo", segundos_restantes=round(q)), camara,
                            revisar_lentes=LENTES_REVISAR,
                            al_lentes=lambda: estado(estado="lentes", mensaje=MENSAJE_LENTES,
                                                     espera_s=round(LENTES_ESPERA_S)),
                            al_buscar=lambda mensaje: estado(estado="buscando", mensaje=mensaje))
        r = registro.resultado()
        if r["cara_detectada_pct"] < 20:
            raise ErrorMedicion("No se vio la cara en casi toda la medición.")
    except ErrorMedicion as e:
        print(f"[vision] ERROR: {e}")
        estado(estado="error", motivo=str(e))
        return None
    mensaje = {"persona": persona, "sesion": sesion, "linea_base": linea_base, **r,
               "ts": datetime.now().replace(microsecond=0).isoformat()}
    guardar_historial(mensaje)
    guardar_trazas(registro, sesion)
    print(json.dumps(mensaje, indent=2, ensure_ascii=False))
    if cli:
        cli.publicar(tema(persona, "vision"), mensaje)
    estado(estado="listo")
    return mensaje


def modo_servicio(cli: ClienteMQTT, camara: str | None = None):
    print("Modo servicio: esperando órdenes en apto/control/orden_vision (Ctrl+C para salir)")
    TRANSMISION.arrancar()
    pendientes: list[dict] = []
    cli.suscribir("apto/control/orden_vision", lambda _t, d: pendientes.append(d))
    try:
        while True:
            if pendientes:
                orden = pendientes.pop(0)
                if orden.get("accion") == "medir":
                    persona = orden.get("persona") or config.get("PERSONA", "bri")
                    segundos = float(orden.get("segundos") or config.get_int("VISION_SEGUNDOS", 60))
                    # "ventana": false = medir sin abrir la ventana (la estación mide la cámara durante la prueba de
                    # reacción y la ventana, que queda adelante, la taparía y le quitaría el teclado).
                    evaluar(persona, segundos, bool(orden.get("linea_base", False)), cli,
                            sesion=orden.get("sesion", ""), camara=camara, ventana=bool(orden.get("ventana", True)))
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


def main():
    ap = argparse.ArgumentParser(description="Parpadeos, PERCLOS y bostezos por cámara")
    ap.add_argument("--listar", action="store_true", help="lista las cámaras")
    ap.add_argument("--ver", action="store_true", help="vista previa en vivo, sin medir")
    ap.add_argument("--persona", help="hace una medición de esta persona")
    ap.add_argument("--segundos", type=float, default=config.get_int("VISION_SEGUNDOS", 60))
    ap.add_argument("--linea-base", action="store_true", help="marca esta medición como línea base")
    ap.add_argument("--servicio", action="store_true", help="espera órdenes por MQTT")
    ap.add_argument("--camara", help="índice o URL (por defecto CAMARA de config.env)")
    ap.add_argument("--sin-ventana", action="store_true", help="mide sin abrir la ventana")
    ap.add_argument("--sin-mqtt", action="store_true", help="no conecta a MQTT (solo muestra el resultado)")
    ap.add_argument("--diagnostico", action="store_true",
                    help="explica en la consola también las aperturas de boca descartadas como bostezo")
    args = ap.parse_args()
    if args.diagnostico:
        global DIAGNOSTICO
        DIAGNOSTICO = True
    sin_modo_eficiencia()

    if args.listar:
        listar_camaras()
        return
    if args.ver:
        try:
            registro = capturar(None, ventana=True, camara=args.camara)
        except ErrorMedicion as e:
            print(f"[vision] {e}")
            return
        if len(registro.t) > 30:  # las series (sin imágenes), para revisar después por qué contó o no un bostezo
            nombre = f"ver-{datetime.now():%Y%m%d-%H%M%S}"
            guardar_trazas(registro, nombre)
            print(f"[vision] Series de la vista previa (sin imágenes): {CARPETA_DATOS / 'trazas' / (nombre + '.npz')}")
        return
    if not (args.servicio or args.persona):
        ap.print_help()
        return

    cli = None
    if not args.sin_mqtt:
        # Solo el servicio es «el módulo de visión» que la estación espera; una medición suelta usa otro nombre.
        cli = ClienteMQTT("vision" if args.servicio else "vision-medicion")
        if not cli.conectar() and args.servicio:
            print("El modo servicio necesita MQTT. Revisen que Mosquitto esté corriendo.")
            return
    if args.servicio:
        modo_servicio(cli, args.camara)
    else:
        evaluar(args.persona.lower(), args.segundos, args.linea_base, cli, ventana=not args.sin_ventana,
                camara=args.camara)
        if cli:
            time.sleep(0.5)  # dar tiempo a que salga el mensaje
            cli.cerrar()


if __name__ == "__main__":
    main()
