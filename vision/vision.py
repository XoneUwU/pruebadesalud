"""Análisis por cámara: pulso sin contacto (rPPG), parpadeos y PERCLOS.

Mira la cara con MediaPipe (FaceLandmarker de Tasks), estima el pulso con el método POS sobre la frente y las
mejillas, mide los ojos con el EAR y publica el resultado en MQTT: apto/{persona}/vision

Modos:
  python vision/vision.py --listar                        lista las cámaras
  python vision/vision.py --ver                           vista previa en vivo, sin medir (q o Esc para salir)
  python vision/vision.py --persona bri                   una medición (VISION_SEGUNDOS, con ventana)
  python vision/vision.py --persona bri --linea-base      igual, marcada como línea base
  python vision/vision.py --referencia 72                 guarda el pulso medido con otro aparato junto al último
                                                          estimado, en datos/vision/validacion.csv
  python vision/vision.py --servicio                      espera órdenes por MQTT (apto/control/orden_vision)

Orden por MQTT (la envía la estación):
  apto/control/orden_vision -> {"accion": "medir", "persona": "bri", "segundos": 60, "linea_base": false, "sesion": "..."}
Mientras mide, abre la ventana de vista previa (la estación le dice a la persona que ahí ve su rostro), publica
apto/control/estado_vision {"estado": "midiendo", "segundos_restantes"} cada 5 s y al final "listo", o "error"
con "motivo". Al terminar cierra la ventana y suelta la cámara.

Cámara: CAMARA en config.env (índice 0, 1… o la URL de DroidCam, como http://IP:4747/video). Por cable USB:
CAMARA=http://127.0.0.1:4747/video; antes de cada medición se rehace «adb forward» hacia el celular.

MÉTODOS
  Pulso (rPPG): promedio RGB de la frente y las dos mejillas en cada cuadro, con su hora. Se vuelve a muestrear a
  30 Hz, se aplica POS (Wang y otros, 2017; ventanas de 1,6 s), se quita la tendencia y se busca el pico del
  espectro (ventana de Hann) solo entre 0,7 y 3 Hz (42 a 180 lpm): ese es el filtro de banda. Calidad: relación
  señal/ruido del pico (de Haan y Jeanne, 2013: potencia a ±0,1 Hz del pico y de su armónico contra el resto de
  la banda), llevada a 0..1 con calidad = (SNR dB + 3) / 12. Con calidad menor que CALIDAD_MIN no se publica el
  número: se avisa.
  Ojos: EAR = (|p2-p6| + |p3-p5|) / (2 |p1-p4|), con 6 puntos por ojo y el promedio de los dos ojos.
  EAR de ojo abierto = mediana de los primeros 5 s. Parpadeo = EAR por debajo del 60 % del abierto durante al
  menos 2 cuadros seguidos. PERCLOS = fracción del tiempo con la cara visible en que el EAR está por debajo del
  30 % del abierto. Es una aproximación del criterio «ojo cerrado al 80 %» (P80): el EAR no llega a 0 con el ojo
  cerrado por cómo caen los puntos, así que el 30 % del valor abierto se usa como equivalente práctico. No está
  validado clínicamente. Los cuadros con la cabeza inclinada más de 15 grados respecto de los primeros 5 s
  (mirando hacia abajo, por ejemplo a un aparato) no cuentan para los ojos: el párpado baja con la mirada y la
  cámara lo vería como cerrado. Cerrar los ojos no mueve la cabeza, así que un cierre real sí cuenta.
  Bostezos: MAR (apertura de la boca) = promedio de 3 aperturas internas de los labios / ancho entre las
  comisuras internas. Bostezo = MAR >= 0,6 que se mantiene (hasta bajar de 0,45) al menos 1,5 s: hablar abre la
  boca menos y por menos tiempo. Durante un bostezo los ojos se achican: esos cuadros no cuentan para los
  parpadeos ni para el PERCLOS.
  Avisos: poca luz, demasiada luz, cara no detectada más del 20 % del tiempo, menos de 15 cuadros por segundo y
  pulso poco confiable.
Es una sugerencia para apoyar la decisión, no un diagnóstico.
"""
import argparse
import csv
import json
import os
import sys
import threading
import time
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
VALIDACION = CARPETA_DATOS / "validacion.csv"
MODELO = config.RAIZ / "modelos" / "face_landmarker.task"
URL_MODELO = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/"
              "face_landmarker.task")
VENTANA = "Vision - Esta apto hoy"

# --- pulso
FS = 30.0                 # Hz, frecuencia a la que se vuelve a muestrear
BANDA = (0.7, 3.0)        # Hz = 42 a 180 lpm
VENTANA_POS_S = 1.6
CALIDAD_MIN = 0.5         # por debajo, no se publica el número del pulso
MIN_SEGUNDOS_PULSO = 6.0
VIVO_SEGUNDOS = 10.0      # ventana del pulso en vivo de la vista previa
# --- ojos
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


def ear_cara(pts: np.ndarray) -> float:
    return (ear(pts[OJO_DER]) + ear(pts[OJO_IZQ])) / 2


def mar(pts: np.ndarray) -> float:
    """MAR (apertura de la boca) = promedio de 3 aperturas verticales internas / ancho entre comisuras internas."""
    ancho = np.linalg.norm(pts[BOCA_COMISURAS[0]] - pts[BOCA_COMISURAS[1]])
    if ancho <= 0:
        return float("nan")
    return float(np.mean([np.linalg.norm(pts[a] - pts[b]) for a, b in BOCA_VERTICAL]) / ancho)


def analizar_boca(t: np.ndarray, mares: np.ndarray) -> dict:
    """Bostezos: MAR >= BOSTEZO_MAR que se mantiene (hasta bajar de BOSTEZO_FIN_MAR) al menos BOSTEZO_MIN_S.

    Devuelve bostezos, bostezos_min y `durante` (máscara de los cuadros de cada bostezo)."""
    t, mares = np.asarray(t, float), np.asarray(mares, float)
    durante = np.zeros(len(t), bool)
    bostezos, inicio = 0, None
    for i, m in enumerate(mares):
        abierta = np.isfinite(m) and (m >= BOSTEZO_MAR or (inicio is not None and m >= BOSTEZO_FIN_MAR))
        if abierta and inicio is None:
            inicio = i
        elif not abierta and inicio is not None:
            if t[i - 1] - t[inicio] >= BOSTEZO_MIN_S:
                bostezos += 1
                durante[inicio:i] = True
            inicio = None
    if inicio is not None and t[-1] - t[inicio] >= BOSTEZO_MIN_S:
        bostezos += 1
        durante[inicio:] = True
    tiempo_cara = float(np.isfinite(mares).sum() / max(len(t), 1) * (t[-1] - t[0])) if len(t) > 1 else 0.0
    return {"bostezos": bostezos, "bostezos_min": round(bostezos / (tiempo_cara / 60), 1) if tiempo_cara > 0 else None,
            "durante": durante}


def regiones(pts: np.ndarray, ancho: int, alto: int) -> list[tuple[int, int, int, int]]:
    """Frente y dos mejillas como rectángulos (x0, y0, x1, y1), a partir de puntos de la malla en píxeles.

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


def remuestrear(t: np.ndarray, rgb: np.ndarray, fs: float = FS) -> np.ndarray:
    """Muestras con horas irregulares (y huecos) -> muestras cada 1/fs s, por interpolación lineal."""
    validas = np.all(np.isfinite(rgb), axis=1)
    t, rgb = t[validas], rgb[validas]
    if len(t) < 2:
        return np.empty((0, 3))
    rejilla = np.arange(t[0], t[-1], 1 / fs)
    return np.column_stack([np.interp(rejilla, t, rgb[:, c]) for c in range(3)])


def pos(rgb: np.ndarray, fs: float = FS) -> np.ndarray:
    """Método POS (Plane-Orthogonal-to-Skin, Wang y otros, 2017): RGB (N x 3) -> señal de pulso (N)."""
    n = len(rgb)
    largo = int(round(VENTANA_POS_S * fs))
    h = np.zeros(n)
    proy = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    for i in range(0, n - largo + 1):
        c = rgb[i:i + largo].T
        media = c.mean(axis=1, keepdims=True)
        if np.any(media <= 0):
            continue
        s = proy @ (c / media)
        d1 = s[1].std()
        hh = s[0] + (s[0].std() / d1 if d1 > 0 else 0.0) * s[1]
        h[i:i + largo] += hh - hh.mean()
    return h


def pulso_espectral(h: np.ndarray, fs: float = FS) -> tuple[float, float]:
    """Pico del espectro entre 0,7 y 3 Hz -> (lpm, SNR en dB)."""
    n = len(h)
    k = np.arange(n)
    x = h - np.polyval(np.polyfit(k, h, 1), k)  # sin tendencia
    x = x * np.hanning(n)
    nfft = max(8192, 1 << int(np.ceil(np.log2(n * 8))))
    p = np.abs(np.fft.rfft(x, nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / fs)
    banda = (f >= BANDA[0]) & (f <= BANDA[1])
    f0 = float(f[banda][np.argmax(p[banda])])
    senal = (np.abs(f - f0) <= 0.1) | (np.abs(f - 2 * f0) <= 0.2)
    ps, pr = p[banda & senal].sum(), p[banda & ~senal].sum()
    snr = 10 * np.log10(ps / pr) if pr > 0 else 30.0
    return f0 * 60, float(snr)


def calidad_de_snr(snr_db: float) -> float:
    return float(np.clip((snr_db + 3) / 12, 0, 1))


def estimar_pulso(t: np.ndarray, rgb: np.ndarray) -> dict | None:
    """{lpm, snr_db, calidad, confiable} o None si hay menos de MIN_SEGUNDOS_PULSO de datos."""
    u = remuestrear(np.asarray(t, float), np.asarray(rgb, float))
    if len(u) < MIN_SEGUNDOS_PULSO * FS:
        return None
    lpm, snr = pulso_espectral(pos(u))
    calidad = calidad_de_snr(snr)
    return {"lpm": round(lpm, 1), "snr_db": round(snr, 2), "calidad": round(calidad, 2), "confiable": calidad >= CALIDAD_MIN}


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
        self.t, self.rgb, self.ear, self.mar, self.brillo, self.saturado = [], [], [], [], [], []
        self.inclinacion = []

    def agregar(self, t: float, pts, cuadro_bgr, inclinacion: float = float("nan")):
        self.t.append(t)
        if pts is None:
            self.rgb.append([np.nan] * 3)
            self.ear.append(np.nan)
            self.mar.append(np.nan)
            self.inclinacion.append(np.nan)
            return
        self.ear.append(ear_cara(pts))
        self.mar.append(mar(pts))
        self.inclinacion.append(inclinacion)
        piel = color_piel(cuadro_bgr, regiones(pts, cuadro_bgr.shape[1], cuadro_bgr.shape[0]))
        if piel is None:
            self.rgb.append([np.nan] * 3)
        else:
            self.rgb.append(list(piel[0]))
            self.brillo.append(piel[1])
            self.saturado.append(piel[2])

    def pulso_reciente(self, segundos: float = VIVO_SEGUNDOS) -> dict | None:
        if not self.t:
            return None
        t = np.asarray(self.t)
        desde = np.searchsorted(t, t[-1] - segundos)
        return estimar_pulso(t[desde:], np.asarray(self.rgb)[desde:])

    def resultado(self) -> dict:
        t = np.asarray(self.t, float)
        duracion = float(t[-1] - t[0]) if len(t) > 1 else 0.0
        cara_pct = float(np.isfinite(np.asarray(self.ear, float)).mean() * 100) if len(t) else 0.0
        fps = (len(t) - 1) / duracion if duracion > 0 else 0.0
        pulso = estimar_pulso(t, np.asarray(self.rgb, float)) if len(t) else None
        boca = analizar_boca(t, np.asarray(self.mar, float)) if len(t) > 1 else None
        ears = np.asarray(self.ear, float).copy()
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
        if pulso is None:
            avisos.append("No hubo datos suficientes para el pulso.")
        elif not pulso["confiable"]:
            avisos.append(f"El pulso por cámara no es confiable (calidad {pulso['calidad']:.2f}): no se da el número.")
        return {
            "pulso_rppg_lpm": pulso["lpm"] if pulso and pulso["confiable"] else None,
            "calidad_rppg": pulso["calidad"] if pulso else None,
            "snr_rppg_db": pulso["snr_db"] if pulso else None,
            "parpadeos_min": ojos["parpadeos_min"] if ojos else None,
            "parpadeos": ojos["parpadeos"] if ojos else None,
            "perclos": ojos["perclos"] if ojos else None,
            "ear_abierto": ojos["ear_abierto"] if ojos else None,
            "cabeza_inclinada_pct": ojos["cabeza_inclinada_pct"] if ojos else None,
            "bostezos": boca["bostezos"] if boca else None,
            "bostezos_min": boca["bostezos_min"] if boca else None,
            "cara_detectada_pct": round(cara_pct, 1),
            "fps": round(fps, 1),
            "duracion_s": round(duracion, 1),
            "brillo_piel": round(brillo, 1) if brillo is not None else None,
            "avisos": avisos,
            "_pulso_crudo_lpm": pulso["lpm"] if pulso else None,  # solo para el historial y la validación
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


def puente_usb(fuente: str) -> str | None:
    """Rehace «adb forward» hacia el puerto de DroidCam (se pierde cada vez que se desconecta el celular).
    None si quedó listo; si no, el motivo para mostrar."""
    import subprocess
    from urllib.parse import urlparse
    adb = buscar_adb()
    if adb is None:
        return "No encontré adb (Android SDK Platform-Tools) para usar DroidCam por cable."

    def correr(*args):
        return subprocess.run([adb, *args], capture_output=True, text=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        dispositivos = leer_dispositivos(correr("devices").stdout)
        listos = [s for s, e in dispositivos.items() if e == "device"]
        if not listos:
            if "unauthorized" in dispositivos.values():
                return "El celular pide permiso: acepten «¿Permitir depuración USB?» en su pantalla."
            return "No veo el celular por USB: revisen el cable (que pase datos) y que la depuración USB esté activa."
        puerto = urlparse(fuente).port or 4747
        r = correr("-s", listos[0], "forward", f"tcp:{puerto}", f"tcp:{puerto}")
        if r.returncode != 0:
            return f"No se pudo conectar el puerto {puerto} por USB: {(r.stderr or r.stdout).strip()}"
    except (OSError, subprocess.SubprocessError) as e:
        return f"adb falló: {e}"
    return None


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


def asegurar_modelo() -> Path:
    if MODELO.exists():
        return MODELO
    import urllib.request
    print(f"[vision] Descargando el modelo de la cara a {MODELO} (una sola vez)...")
    MODELO.parent.mkdir(parents=True, exist_ok=True)
    try:
        urllib.request.urlretrieve(URL_MODELO, MODELO)
    except OSError as e:
        raise ErrorMedicion(f"Falta {MODELO.name} y no se pudo descargar ({e}). Corran instalar.bat.") from e
    return MODELO


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

    def puntos(self, cuadro_bgr, t_s: float):
        import cv2
        ms = max(int(t_s * 1000), self._ultimo_ms + 1)  # el modo video exige horas crecientes
        self._ultimo_ms = ms
        rgb = cv2.cvtColor(cuadro_bgr, cv2.COLOR_BGR2RGB)
        r = self._lm.detect_for_video(self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb), ms)
        if not r.face_landmarks:
            self.inclinacion = float("nan")
            return None
        self.inclinacion = float("nan")
        if getattr(r, "facial_transformation_matrixes", None):
            rot = np.asarray(r.facial_transformation_matrixes[0], float)[:3, :3]
            self.inclinacion = float(np.degrees(np.arctan2(rot[2, 1], rot[2, 2])))  # giro sobre el eje horizontal
        h, w = cuadro_bgr.shape[:2]
        return np.array([(p.x * w, p.y * h) for p in r.face_landmarks[0]])

    def cerrar(self):
        self._lm.close()


# ================================================================ vista previa
def dibujar(cuadro, pts, conexiones, info: dict):
    """Malla, regiones del pulso, ojos y un panel con el pulso, el EAR y el tiempo (texto sin tildes: OpenCV)."""
    import cv2
    capa = cuadro.copy()
    if pts is not None:
        segmentos = pts[conexiones].astype(np.int32)
        cv2.polylines(capa, segmentos, False, (200, 170, 90), 1, cv2.LINE_AA)
        for x0, y0, x1, y1 in regiones(pts, cuadro.shape[1], cuadro.shape[0]):
            cv2.rectangle(capa, (x0, y0), (x1, y1), (80, 220, 80), 2)
        for i in OJO_DER + OJO_IZQ:
            cv2.circle(capa, tuple(pts[i].astype(int)), 2, (40, 210, 255), -1, cv2.LINE_AA)
    cuadro[:] = cv2.addWeighted(capa, 0.75, cuadro, 0.25, 0)
    h, w = cuadro.shape[:2]
    panel = cuadro.copy()
    cv2.rectangle(panel, (0, 0), (w, 118), (12, 16, 22), -1)
    cuadro[:118] = cv2.addWeighted(panel[:118], 0.78, cuadro[:118], 0.22, 0)
    blanco, gris, verde, amarillo = (240, 240, 240), (170, 170, 170), (110, 220, 110), (60, 200, 255)
    cv2.putText(cuadro, "APTO HOY  -  VISION", (14, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, gris, 1, cv2.LINE_AA)
    p = info.get("pulso")
    if pts is None:
        texto, color = "NO SE VE LA CARA", amarillo
    elif p is None:
        texto, color = "PULSO  calculando...", blanco
    elif not p["confiable"]:
        texto, color = f"PULSO  senal debil (calidad {p['calidad']:.2f})", amarillo
    else:
        texto, color = f"PULSO  {p['lpm']:.0f} lpm  (calidad {p['calidad']:.2f})", verde
    cv2.putText(cuadro, texto, (14, 60), cv2.FONT_HERSHEY_DUPLEX, 0.85, color, 1, cv2.LINE_AA)
    e = info.get("ear")
    ojos = f"EAR  {e:.2f}" if e is not None and np.isfinite(e) else "EAR  -"
    if info.get("parpadeos") is not None:
        ojos += f"     PARPADEOS  {info['parpadeos']}"
    if info.get("bostezos") is not None:
        ojos += f"     BOSTEZOS  {info['bostezos']}"
    cv2.putText(cuadro, ojos, (14, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.65, blanco, 1, cv2.LINE_AA)
    if info.get("boca_abierta"):
        cv2.putText(cuadro, "BOCA MUY ABIERTA (posible bostezo)", (w - 430, 92), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    amarillo, 2, cv2.LINE_AA)
    derecha = f"QUEDAN {info['quedan']:.0f} s" if info.get("quedan") is not None else "VISTA PREVIA  (q para salir)"
    (tw, _), _ = cv2.getTextSize(derecha, cv2.FONT_HERSHEY_DUPLEX, 0.75, 1)
    cv2.putText(cuadro, derecha, (w - tw - 14, 60), cv2.FONT_HERSHEY_DUPLEX, 0.75, blanco, 1, cv2.LINE_AA)
    for i, aviso in enumerate(info.get("avisos", [])):
        cv2.putText(cuadro, aviso, (14, h - 18 - 26 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.6, amarillo, 2, cv2.LINE_AA)
    if info.get("progreso") is not None:
        cv2.rectangle(cuadro, (0, h - 6), (int(w * info["progreso"]), h), (90, 200, 255), -1)
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


def capturar(segundos: float | None, ventana: bool = True, al_avanzar=None, camara: str | None = None) -> Registro:
    """Abre la cámara y junta cuadros durante `segundos` (None = hasta q/Esc). al_avanzar(quedan) cada 5 s."""
    import cv2
    fuente = fuente_camara(camara)
    if es_usb(fuente):
        motivo = puente_usb(fuente)
        if motivo:
            raise ErrorMedicion(motivo)
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
        raise ErrorMedicion(f"No se pudo abrir la cámara {fuente}.{extra}")
    rostro = Rostro()
    registro = Registro()
    cam = None
    try:
        cuadro = primer_cuadro(cap)
        if cuadro is None:
            raise ErrorMedicion(f"La cámara {fuente} no entrega imágenes.")
        if es_plano(cuadro):
            raise ErrorMedicion(f"La cámara {fuente} entrega una imagen plana, sin video (si es la cámara virtual de "
                                f"DroidCam, usen la URL del celular en CAMARA).")
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
        inicio = time.perf_counter()
        ultimo_aviso, vivo, ultimo_vivo, parpadeos, bostezos = -5.0, None, 0.0, None, None
        while True:
            cuadro, llegada = cam.siguiente()
            if cuadro is None:
                raise ErrorMedicion("La cámara dejó de enviar imágenes.")
            t = llegada - inicio  # la hora en que llegó el cuadro, no la de procesarlo
            cuadro = cv2.flip(cuadro, 1)  # como un espejo
            pts = rostro.puntos(cuadro, t)
            registro.agregar(t, pts, cuadro, rostro.inclinacion)
            quedan = None if segundos is None else max(0.0, segundos - t)
            if al_avanzar and quedan is not None and t - ultimo_aviso >= 5:
                ultimo_aviso = t
                al_avanzar(quedan)
            if ventana:
                if t - ultimo_vivo >= 1.0:  # el pulso y los parpadeos en vivo se recalculan una vez por segundo
                    ultimo_vivo, vivo = t, registro.pulso_reciente()
                    if t > CALIBRACION_S:  # también en --ver
                        ojos = analizar_ojos(np.asarray(registro.t), np.asarray(registro.ear), registro.inclinacion)
                        parpadeos = ojos["parpadeos"] if ojos else None
                    if len(registro.t) > 1:
                        bostezos = analizar_boca(np.asarray(registro.t), np.asarray(registro.mar))["bostezos"]
                info = {"pulso": vivo, "ear": registro.ear[-1], "parpadeos": parpadeos, "quedan": quedan,
                        "bostezos": bostezos, "boca_abierta": np.isfinite(registro.mar[-1]) and registro.mar[-1] >= BOSTEZO_MAR,
                        "progreso": None if segundos is None else min(1.0, t / segundos),
                        "avisos": avisos_en_vivo(registro)}
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
    finally:
        if cam is not None:
            cam.cerrar()
        else:
            cap.release()
        rostro.cerrar()
        if ventana:
            cv2.destroyWindow(VENTANA)
            cv2.waitKey(1)
    return registro


# ================================================================ flujo completo
def guardar_historial(mensaje: dict, crudo):
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(HISTORIAL, "a", encoding="utf-8") as f:
        f.write(json.dumps({**mensaje, "pulso_crudo_lpm": crudo}, ensure_ascii=False) + "\n")


def guardar_validacion(medicion: dict, referencia: float):
    """Una fila de datos/vision/validacion.csv: el pulso estimado junto al medido con otro aparato."""
    crudo = medicion.get("pulso_crudo_lpm")
    fila = {
        "fecha": medicion.get("ts") or datetime.now().replace(microsecond=0).isoformat(),
        "persona": medicion.get("persona"), "sesion": medicion.get("sesion"),
        "pulso_referencia_lpm": referencia, "pulso_rppg_lpm": medicion.get("pulso_rppg_lpm"),
        "pulso_crudo_lpm": crudo, "error_lpm": round(crudo - referencia, 1) if crudo is not None else None,
        "calidad_rppg": medicion.get("calidad_rppg"), "snr_rppg_db": medicion.get("snr_rppg_db"),
        "fps": medicion.get("fps"), "cara_detectada_pct": medicion.get("cara_detectada_pct"),
        "duracion_s": medicion.get("duracion_s"), "avisos": " | ".join(medicion.get("avisos") or []),
    }
    nuevo = not VALIDACION.exists()
    CARPETA_DATOS.mkdir(parents=True, exist_ok=True)
    with open(VALIDACION, "a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila))
        if nuevo:
            w.writeheader()
        w.writerow(fila)
    print(f"Validación guardada en {VALIDACION}: estimado {crudo} lpm, referencia {referencia} lpm, "
          f"error {fila['error_lpm']} lpm (calidad {fila['calidad_rppg']}).")


def guardar_trazas(registro: Registro, sesion: str):
    """Series numéricas de la medición (sin imágenes): hora, RGB de la piel y EAR por cuadro, para validar y
    mejorar el cálculo después. datos/vision/trazas/{sesion}.npz"""
    carpeta = CARPETA_DATOS / "trazas"
    carpeta.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(carpeta / f"{sesion}.npz", t=np.asarray(registro.t), rgb=np.asarray(registro.rgb, float),
                        ear=np.asarray(registro.ear, float), mar=np.asarray(registro.mar, float),
                        inclinacion=np.asarray(registro.inclinacion, float))


def ultima_medicion() -> dict | None:
    if not HISTORIAL.exists():
        return None
    lineas = [x for x in HISTORIAL.read_text(encoding="utf-8").splitlines() if x.strip()]
    return json.loads(lineas[-1]) if lineas else None


def evaluar(persona: str, segundos: float, linea_base: bool, cli: ClienteMQTT | None, sesion: str = "",
            ventana: bool = True, referencia: float | None = None, camara: str | None = None) -> dict | None:
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    sesion = sesion or marca

    def estado(**datos):
        if cli:
            cli.publicar("apto/control/estado_vision", {"persona": persona, "sesion": sesion, **datos})

    print(f"[vision] Midiendo a {persona} durante {segundos:.0f} s...")
    try:
        registro = capturar(segundos, ventana, lambda q: estado(estado="midiendo", segundos_restantes=round(q)), camara)
        r = registro.resultado()
        if r["cara_detectada_pct"] < 20:
            raise ErrorMedicion("No se vio la cara en casi toda la medición.")
    except ErrorMedicion as e:
        print(f"[vision] ERROR: {e}")
        estado(estado="error", motivo=str(e))
        return None
    crudo = r.pop("_pulso_crudo_lpm")
    mensaje = {"persona": persona, "sesion": sesion, "linea_base": linea_base, **r,
               "ts": datetime.now().replace(microsecond=0).isoformat()}
    guardar_historial(mensaje, crudo)
    guardar_trazas(registro, sesion)
    print(json.dumps(mensaje, indent=2, ensure_ascii=False))
    print(f"[vision] Pulso estimado (aunque sea dudoso): {crudo} lpm")
    if cli:
        cli.publicar(tema(persona, "vision"), mensaje)
    estado(estado="listo")
    if referencia is not None:
        guardar_validacion({**mensaje, "pulso_crudo_lpm": crudo}, referencia)
    return mensaje


def modo_servicio(cli: ClienteMQTT, camara: str | None = None):
    print("Modo servicio: esperando órdenes en apto/control/orden_vision (Ctrl+C para salir)")
    pendientes: list[dict] = []
    cli.suscribir("apto/control/orden_vision", lambda _t, d: pendientes.append(d))
    try:
        while True:
            if pendientes:
                orden = pendientes.pop(0)
                if orden.get("accion") == "medir":
                    persona = orden.get("persona") or config.get("PERSONA", "bri")
                    segundos = float(orden.get("segundos") or config.get_int("VISION_SEGUNDOS", 60))
                    evaluar(persona, segundos, bool(orden.get("linea_base", False)), cli,
                            sesion=orden.get("sesion", ""), camara=camara)
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nSaliendo.")


def main():
    ap = argparse.ArgumentParser(description="Pulso sin contacto, parpadeos y PERCLOS por cámara")
    ap.add_argument("--listar", action="store_true", help="lista las cámaras")
    ap.add_argument("--ver", action="store_true", help="vista previa en vivo, sin medir")
    ap.add_argument("--persona", help="hace una medición de esta persona")
    ap.add_argument("--segundos", type=float, default=config.get_int("VISION_SEGUNDOS", 60))
    ap.add_argument("--linea-base", action="store_true", help="marca esta medición como línea base")
    ap.add_argument("--referencia", type=float, help="pulso medido con otro aparato (lpm), para la validación")
    ap.add_argument("--servicio", action="store_true", help="espera órdenes por MQTT")
    ap.add_argument("--camara", help="índice o URL (por defecto CAMARA de config.env)")
    ap.add_argument("--sin-ventana", action="store_true", help="mide sin abrir la ventana")
    ap.add_argument("--sin-mqtt", action="store_true", help="no conecta a MQTT (solo muestra el resultado)")
    args = ap.parse_args()

    if args.listar:
        listar_camaras()
        return
    if args.ver:
        try:
            capturar(None, ventana=True, camara=args.camara)
        except ErrorMedicion as e:
            print(f"[vision] {e}")
        return
    if args.referencia is not None and not args.persona:
        ultima = ultima_medicion()
        if not ultima:
            print("No hay mediciones en datos/vision/historial.jsonl. Midan primero con --persona.")
            return
        guardar_validacion(ultima, args.referencia)
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
                referencia=args.referencia, camara=args.camara)
        if cli:
            time.sleep(0.5)  # dar tiempo a que salga el mensaje
            cli.cerrar()


if __name__ == "__main__":
    main()
