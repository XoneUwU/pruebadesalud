"""Entrada y salida de voz del copiloto: grabar, transcribir (Whisper) y hablar (Piper o voz de Windows)."""
import io
import queue
import re
import threading
import wave
from pathlib import Path

import numpy as np

from comun import config

FS = 16000
# Piper deja muy poco silencio al final y la salida de audio tarda en arrancar y en vaciarse:
# sin este margen, a veces se cortaba la última palabra.
SILENCIO_INICIO_S = 0.1
SILENCIO_FINAL_S = 0.4


# ---------------------------------------------------------------- micrófono
def grabar_hasta_enter(destino: Path, max_s: int = 30) -> Path | None:
    """Graba desde que se llama hasta que la persona presiona Enter (máximo max_s segundos)."""
    import sounddevice as sd
    import soundfile as sf

    disp = config.get("MIC_DISPOSITIVO")
    disp = int(disp) if disp.isdigit() else None
    trozos: list[np.ndarray] = []

    def callback(indata, frames, tiempo, status):
        if sum(len(t) for t in trozos) < max_s * FS:
            trozos.append(indata.copy())

    with sd.InputStream(samplerate=FS, channels=1, dtype="float32", device=disp, callback=callback):
        input("   Escuchando... presiona Enter cuando termines de hablar. ")
    if not trozos:
        return None
    audio = np.concatenate(trozos)
    if len(audio) < FS * 0.4:  # menos de 0,4 s: probablemente vacío
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    sf.write(destino, audio, FS)
    return destino


# ---------------------------------------------------------------- Whisper
class Transcriptor:
    """Whisper local con faster-whisper. El modelo se carga la primera vez que se usa."""

    def __init__(self):
        self._modelo = None

    def cargar(self):
        if self._modelo is None:
            from faster_whisper import WhisperModel
            nombre = config.get("WHISPER_MODEL", "small")
            dispositivo = config.get("WHISPER_DEVICE", "cpu")
            tipo = "float16" if dispositivo == "cuda" else "int8"
            print(f"[copiloto] Cargando Whisper '{nombre}' en {dispositivo}...")
            self._modelo = WhisperModel(nombre, device=dispositivo, compute_type=tipo)
        return self._modelo

    def transcribir(self, ruta_wav: Path) -> str:
        # Se lee el audio con soundfile y se pasa como arreglo: así no se usa PyAV, cuyas
        # versiones nuevas no son compatibles con faster-whisper 1.2.1.
        audio = leer_audio_16k(ruta_wav)
        segmentos, _ = self.cargar().transcribe(audio, language="es", beam_size=1, vad_filter=True)
        return " ".join(s.text.strip() for s in segmentos).strip()


def leer_audio_16k(ruta_wav: Path) -> np.ndarray:
    """Lee un .wav como float32 mono a 16 kHz, que es lo que espera Whisper."""
    import soundfile as sf

    audio, fs = sf.read(str(ruta_wav), dtype="float32", always_2d=True)
    audio = audio.mean(axis=1)  # a mono
    if fs != FS:
        n = int(round(len(audio) * FS / fs))
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)
    return audio


# ---------------------------------------------------------------- pronunciación
def leer_pronunciacion(valor: str) -> dict[str, str]:
    """"Xone:Yone, PVT:pe ve te" -> {"xone": "Yone", "pvt": "pe ve te"} (PRONUNCIAR en config.env)."""
    pares = {}
    for par in (valor or "").split(","):
        palabra, _, lectura = par.partition(":")
        if palabra.strip() and lectura.strip():
            pares[palabra.strip().lower()] = lectura.strip()
    return pares


def aplicar_pronunciacion(texto: str, pares: dict[str, str]) -> str:
    """Reemplaza palabras completas sin importar mayúsculas. Solo para el texto que va a la voz."""
    if not pares:
        return texto
    palabras = sorted(pares, key=len, reverse=True)  # primero las más largas
    patron = r"(?<!\w)(" + "|".join(re.escape(p) for p in palabras) + r")(?!\w)"
    return re.sub(patron, lambda m: pares[m.group(0).lower()], texto, flags=re.IGNORECASE)


# ---------------------------------------------------------------- Piper
def velocidad_piper() -> float:
    """PIPER_VELOCIDAD de config.env (length_scale de Piper): 1.0 es normal y más alto es más lento."""
    valor = config.get("PIPER_VELOCIDAD", "1.0")
    try:
        velocidad = float(valor.replace(",", "."))
    except ValueError:
        velocidad = 0
    if velocidad <= 0:
        print(f"[copiloto] PIPER_VELOCIDAD no válida ({valor!r}); se usa 1.0.")
        return 1.0
    return velocidad


def cargar_piper(ruta: Path):
    try:
        from piper import PiperVoice           # piper-tts 1.3 o más nuevo
    except ImportError:
        from piper.voice import PiperVoice     # piper-tts 1.2
    return PiperVoice.load(str(ruta))


def sintetizar_piper(voz, texto: str, velocidad: float = 1.0) -> tuple[np.ndarray, int]:
    """Texto -> (audio, frecuencia de muestreo), en memoria."""
    import soundfile as sf

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        if hasattr(voz, "synthesize_wav"):     # piper-tts 1.3 o más nuevo
            from piper import SynthesisConfig
            voz.synthesize_wav(texto, wf, syn_config=SynthesisConfig(length_scale=velocidad))
        else:                                  # piper-tts 1.2
            voz.synthesize(texto, wf, length_scale=velocidad)
    buf.seek(0)
    datos, fs = sf.read(buf, dtype="float32")
    return datos, fs


def reproducir(datos: np.ndarray, fs: int):
    """Reproduce el audio con un margen de silencio al inicio y al final (ver SILENCIO_FINAL_S)."""
    import sounddevice as sd

    margen = [(int(SILENCIO_INICIO_S * fs), int(SILENCIO_FINAL_S * fs))] + [(0, 0)] * (datos.ndim - 1)
    sd.play(np.pad(datos, margen), fs)
    sd.wait()


# ---------------------------------------------------------------- voz de salida
class Locutor:
    """Habla en un hilo aparte para no bloquear el programa.

    Orden de preferencia: Piper (voz natural) -> voz de Windows (pyttsx3) -> solo texto.
    """

    def __init__(self, activo: bool = True):
        self.activo = activo
        self._cola: queue.Queue[str | None] = queue.Queue()
        self.motor = "texto"
        self._pronunciar = leer_pronunciacion(config.get("PRONUNCIAR"))
        if activo:
            if self._pronunciar:
                print(f"[copiloto] Pronunciación: {', '.join(f'{p} -> {lec}' for p, lec in self._pronunciar.items())}")
            threading.Thread(target=self._trabajar, daemon=True).start()

    def decir(self, texto: str):
        print(f"\n   COPILOTO: {texto}\n")  # en pantalla, el texto original
        if self.activo:
            self._cola.put(aplicar_pronunciacion(texto, self._pronunciar))  # a la voz, con la pronunciación

    def esperar(self):
        """Espera a que termine de hablar todo lo pendiente."""
        if self.activo:
            self._cola.join()

    # --- hilo de trabajo ---
    def _trabajar(self):
        hablar = self._preparar_motor()
        while True:
            texto = self._cola.get()
            try:
                if texto and hablar:
                    hablar(texto)
            except Exception as e:
                print(f"[copiloto] Error al hablar: {e}")
            finally:
                self._cola.task_done()

    def _preparar_motor(self):
        piper = self._preparar_piper()
        if piper:
            self.motor = "piper"
            return piper
        windows = self._preparar_pyttsx3()
        if windows:
            self.motor = "windows"
            return windows
        print("[copiloto] Sin motor de voz: las respuestas solo se muestran en pantalla.")
        return None

    def _preparar_piper(self):
        ruta = config.ruta("PIPER_VOZ")
        if not ruta or not ruta.exists():
            return None
        try:
            import sounddevice  # noqa: F401  (solo para comprobar que está instalado)
            import soundfile    # noqa: F401
            voz = cargar_piper(ruta)
        except Exception as e:
            print(f"[copiloto] Piper no disponible ({e}); se usará la voz de Windows.")
            return None
        velocidad = velocidad_piper()

        def hablar(texto: str):
            reproducir(*sintetizar_piper(voz, texto, velocidad))

        print(f"[copiloto] Voz: Piper ({ruta.name}, velocidad {velocidad})")
        return hablar

    def _preparar_pyttsx3(self):
        try:
            try:
                import pythoncom  # necesario en Windows al usar la voz desde un hilo
                pythoncom.CoInitialize()
            except ImportError:
                pass
            import pyttsx3
            motor = pyttsx3.init()
            for v in motor.getProperty("voices"):
                nombre = f"{v.id} {v.name} {getattr(v, 'languages', '')}".lower()
                if any(x in nombre for x in ("spanish", "español", "es-", "es_", "sabina", "helena", "laura")):
                    motor.setProperty("voice", v.id)
                    break
            motor.setProperty("rate", 175)
        except Exception as e:
            print(f"[copiloto] Voz de Windows no disponible ({e}).")
            return None

        def hablar(texto: str):
            motor.say(texto)
            motor.runAndWait()

        print("[copiloto] Voz: Windows (pyttsx3)")
        return hablar
