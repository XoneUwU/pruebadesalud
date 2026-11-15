"""Copiloto por voz de «¿Está apto hoy?».

- Escucha las evaluaciones del coordinador (apto/+/evaluacion) y explica el semáforo en voz alta.
- Responde preguntas habladas o escritas usando SOLO las fichas de protocolo y la evaluación actual.
- Publica cada respuesta en apto/{persona}/copiloto para que el resto del equipo la vea en la interfaz.
- «Soy Eric», «habla Sebas» o «aquí Bri» cambia la persona activa (nombres de TRIPULACION en config.env).

Uso:
  python copiloto/copiloto.py                     modo completo (micrófono + voz)
  python copiloto/copiloto.py --texto             preguntas escritas (no carga Whisper)
  python copiloto/copiloto.py --texto --sin-voz   solo texto en pantalla, ideal para probar
  python copiloto/copiloto.py --sin-llm           sin Ollama: responde con las fichas

Temas MQTT:
  lee      apto/+/evaluacion       evaluación del coordinador (mejor si viene con retain)
  lee      apto/control/sesion     {"persona": "eric", "tarea": "caminata espacial"} cambia la persona activa
  lee      apto/control/pregunta   {"persona": "eric", "pregunta": "..."} pregunta enviada desde un panel
  publica  apto/{persona}/copiloto {"pregunta", "respuesta", "fichas", "modo", "origen"}
  publica  apto/control/sesion     {"persona", "tarea"} cuando alguien se identifica («soy Eric»)
"""
import argparse
import difflib
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from buscador import Buscador
from habla import Locutor, Transcriptor, grabar_hasta_enter, grabar_hasta_silencio
from llm import CerebroLLM

from comun import config
from comun.mqtt_cliente import ClienteMQTT, persona_de_tema, tema

# Camino de alarma (texto fijo, sin el modelo): hasta 2 medidas de la ficha + AVISO + ADVERTENCIA.
# El médico de vuelo está en Tierra; a bordo hay un responsable médico de la tripulación.
AVISO = ("Avisa al comandante y al responsable médico de la tripulación y, si hay comunicación, "
         "al médico de vuelo en Tierra.")
ADVERTENCIA = "Esto es solo una sugerencia temporal: busca atención de personal capacitado lo antes posible."
MEDIDA_SIN_FICHA = "Detén la tarea y quédate en un lugar seguro."
# Aviso de SpO2 del coordinador ("aviso_spo2": true): no cambia el color; el resumen lo dice al final.
AVISO_SPO2 = "Aviso: el oxígeno en sangre salió más bajo de lo habitual; repite la medición."

# Recordatorio fijo (sin el modelo) al final de las respuestas cuya ficha principal es de salud.
RECORDATORIO = "Si no mejora, busca la ayuda de personal capacitado."
FICHAS_DE_SALUD = ("Falta de sueño", "Reacción lenta y lapsos de atención", "Ojos cansados y somnolencia",
                   "Estrés y variabilidad del pulso", "Pulso en reposo elevado", "Oxígeno en sangre bajo",
                   "Fatiga en la voz")

CARPETA_AUDIO = config.RAIZ / "datos" / "copiloto"
PALABRAS_RESULTADO = ("por qué", "porque", "semáforo", "semaforo", "resultado", "color", "apto",
                      "estoy", "amarillo", "rojo", "verde", "mi evaluación", "mi evaluacion", "puedo")


def _minuscula_inicial(texto: str) -> str:
    # "Reacción más lenta" -> "reacción más lenta", pero "PVT alta" queda igual
    if len(texto) > 1 and texto[1].islower():
        return texto[0].lower() + texto[1:]
    return texto


def _unir(items: list[str]) -> str:
    items = [_minuscula_inicial(i.strip().rstrip(".")) for i in items if i and i.strip()]
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


PALABRAS_TRIPULACION = ("quién", "quien", "alguien", "alguno", "alguna", "tripulación", "tripulacion",
                        "compañero", "companero", "pasajero", "equipo", "otra persona", "los demás",
                        "los demas", "nadie")
ORDEN_COLOR = {"verde": 0, "amarillo": 1, "rojo": 2}

# Síntomas de alarma: si la pregunta menciona alguno, se responde con respuesta_alarma(),
# antes que cualquier otro camino. Se buscan en minúsculas y sin tildes.
_ALARMA = re.compile(
    r"\b(falta(n)? (de |el )?aire|no puedo respirar|me cuesta respirar"
    r"|dolor (de|en el) pecho|me duele el pecho"
    r"|mareos?|maread[oa]s?"
    r"|confusion|confundid[oa]s?"
    r"|desmay\w*)\b"  # desmayo, desmayar, me voy a desmayar, me desmayé
)

# Tareas que llevan "el" en vez de "la" (resumen: "para el mantenimiento del filtro").
TAREAS_CON_EL = ("mantenimiento", "experimento", "acoplamiento", "control")


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes: "Mareada" -> "mareada", "Confusión" -> "confusion"."""
    texto = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in texto if unicodedata.category(c) != "Mn")


# «Soy Eric», «habla Sebas», «aquí Bri» (con o sin «hola» delante): cambia la persona activa.
_IDENTIFICACION = re.compile(r"^[\s¡¿]*(?:hola[\s,.!]+)?(soy|habla|aqu[ií])\s+([^\W\d_]+)(.*)$",
                             re.IGNORECASE | re.DOTALL)
SIMILITUD_NOMBRE = 0.7  # difflib: "erik" se parece 0,75 a "eric"; "diego" no llega a 0,7 con nadie


def leer_tripulacion(valor: str) -> list[str]:
    """"bri, Danilo,sebas" -> ["bri", "danilo", "sebas"] (TRIPULACION en config.env)."""
    return [p.strip().lower() for p in (valor or "").split(",") if p.strip()]


def identificar(pregunta: str, tripulacion: list[str]) -> tuple[str | None, str] | None:
    """Si la pregunta empieza con «soy X», «habla X» o «aquí X», devuelve (persona, resto).

    persona: el nombre de la tripulación que más se parece a X (sin importar tildes ni mayúsculas,
    porque Whisper puede escribir "Erik"), o None si no se parece a ninguno. resto: lo que sigue
    al nombre ("Soy Eric, me falta el aire" -> "me falta el aire"); vacío si solo se identificó.
    Devuelve None si la pregunta no es una identificación o no hay tripulación configurada.
    """
    m = _IDENTIFICACION.match(pregunta or "")
    if not m or not tripulacion:
        return None
    resto = m.group(3).lstrip(" \t,.;:!?¡¿-")
    if not re.search(r"\w", resto):
        resto = ""
    por_normal = {_normalizar(p): p for p in tripulacion}
    parecidos = difflib.get_close_matches(_normalizar(m.group(2)), list(por_normal), n=1, cutoff=SIMILITUD_NOMBRE)
    return (por_normal[parecidos[0]] if parecidos else None), resto


def pregunta_sobre_resultado(pregunta: str) -> bool:
    return any(p in pregunta.lower() for p in PALABRAS_RESULTADO)


def pregunta_sobre_tripulacion(pregunta: str) -> bool:
    return any(p in pregunta.lower() for p in PALABRAS_TRIPULACION)


def es_alarma(pregunta: str) -> bool:
    return bool(_ALARMA.search(_normalizar(pregunta)))


def respuesta_alarma(fichas: list) -> str:
    """Hasta 2 medidas de la ficha encontrada, después AVISO y al final ADVERTENCIA.

    Medidas = frases de la ficha que no repiten el aviso (sin "avisa"/"avisar"). Sin ficha con
    medidas, se usa MEDIDA_SIN_FICHA. No usa el modelo: en una emergencia solo se dice texto
    revisado por el equipo.
    """
    medidas = []
    if fichas:
        frases = re.split(r"(?<=[.!?])\s+", fichas[0].texto.replace("\n", " "))
        medidas = [f.strip() for f in frases if f.strip() and "avisa" not in _normalizar(f)][:2]
    return " ".join((medidas or [MEDIDA_SIN_FICHA]) + [AVISO, ADVERTENCIA])


def _puntaje(ev: dict) -> float:
    try:
        return float(ev.get("puntaje") or 0)
    except (TypeError, ValueError):
        return 0.0


def _lista(items: list[str]) -> str:
    """["Sebas"] -> "Sebas"; ["Sebas", "Ana", "Eric"] -> "Sebas, Ana y Eric"."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1]


def con_articulo(tarea: str) -> str:
    """"caminata espacial" -> "la caminata espacial"; "mantenimiento del filtro" -> "el mantenimiento del filtro"."""
    tarea = (tarea or "").strip()
    if not tarea:
        return ""
    inicio = _normalizar(tarea)
    if inicio.split()[0] in ("el", "la", "los", "las", "un", "una"):
        return tarea  # ya trae su artículo
    return ("el " if inicio.startswith(TAREAS_CON_EL) else "la ") + tarea


def mejor_en_verde(evaluaciones: dict[str, dict], excepto: str = "") -> dict | None:
    """La evaluación en verde con mayor puntaje, sin contar a la persona indicada."""
    verdes = [e for p, e in evaluaciones.items() if p != excepto and e.get("color") == "verde"]
    return max(verdes, key=_puntaje) if verdes else None


def resumen_tripulacion(evaluaciones: dict[str, dict], tarea: str = "", persona_activa: str = "") -> str:
    """Quién está más apto para la tarea, según las evaluaciones recibidas (respuesta fija).

    A la persona activa (la que pregunta) se le habla de tú.
    """
    evs = [e for e in evaluaciones.values() if e.get("color") in ORDEN_COLOR]
    if not evs:
        return ("Todavía no hay evaluaciones de la tripulación. Cada persona debe hacer su evaluación "
                "para que pueda recomendar quién hace la tarea.")
    evs.sort(key=lambda e: (ORDEN_COLOR[e["color"]], -_puntaje(e)))
    para = f" para {con_articulo(tarea)}" if tarea else ""

    def es_activa(e: dict) -> bool:
        return e.get("persona") == persona_activa

    def nombre(e: dict) -> str:
        return (e.get("persona") or "").capitalize()

    mejor, resto = evs[0], evs[1:]
    quien = "eres tú" if es_activa(mejor) else f"es {nombre(mejor)}"
    if mejor["color"] == "verde":
        partes = [f"La persona más apta{para} {quien}, en verde."]
    else:
        partes = [f"Nadie está en verde{para}. La opción menos riesgosa {quien}, en {mejor['color']}: "
                  "conviene hacerla en pareja o posponerla."]

    def grupo(color: str) -> tuple[list[str], str]:
        """Quienes tienen ese color (tú primero) y el verbo que concuerda: (["tú", "Adrian"], "están")."""
        es = [e for e in resto if e["color"] == color]
        nombres = (["tú"] if any(es_activa(e) for e in es) else []) + [nombre(e) for e in es if not es_activa(e)]
        verbo = "están" if len(nombres) > 1 else ("estás" if nombres == ["tú"] else "está")
        return nombres, verbo

    # Los demás en verde, juntos: "También están en verde Sebas y Ana." / "Tú y Sebas también están en verde."
    nombres, verbo = grupo("verde")
    if "tú" in nombres:
        texto = f"{_lista(nombres)} también {verbo} en verde."
        partes.append(texto[0].upper() + texto[1:])
    elif nombres:
        partes.append(f"También {verbo} en verde {_lista(nombres)}.")

    # Amarillo y rojo, un grupo por color: "Tú y Adrian están en amarillo, y Danilo está en rojo."
    grupos = []
    for color in ("amarillo", "rojo"):
        nombres, verbo = grupo(color)
        if nombres:
            grupos.append((nombres, f"{_lista(nombres)} {verbo} en {color}"))
    if grupos:
        # con coma antes de la "y" si algún grupo ya tiene la suya, para que se entienda al oírlo
        separador = ", y " if any(len(n) > 1 for n, _ in grupos) else " y "
        texto = separador.join(frase for _, frase in grupos)
        partes.append(texto[0].upper() + texto[1:] + ".")

    if len(evs) == 1:
        partes.append("Solo tengo la evaluación de una persona; faltan las demás.")
    return " ".join(partes)


def resumen(ev: dict, tarea_activa: str = "") -> str:
    """Explicación corta y fija del semáforo (no usa el modelo de lenguaje: es instantánea)."""
    nombre = (ev.get("persona") or "").capitalize()
    color = ev.get("color", "sin color")
    tarea = ev.get("tarea") or tarea_activa
    partes = [f"{nombre}, tu resultado{' para ' + con_articulo(tarea) if tarea else ''} es {color}."]
    aviso_spo2 = bool(ev.get("aviso_spo2"))
    # El aviso de SpO2 no es un motivo del color: se dice aparte, al final.
    motivos = [m for m in (ev.get("motivos") or []) if not (aviso_spo2 and m.lower().startswith("oxígeno más bajo"))]
    if motivos:
        partes.append(f"Motivos: {_unir(motivos)}.")
    elif color == "verde" and not aviso_spo2:
        partes.append("Tus señales están en tu rango habitual.")
    if ev.get("accion"):
        partes.append(f"Recomendación: {_minuscula_inicial(ev['accion'].strip().rstrip('.'))}.")
    if aviso_spo2:
        partes.append(AVISO_SPO2)
    return " ".join(partes)


# ---------------------------------------------------------------- filtro de contradicciones
# Revisa el texto del modelo frase por frase, en minúsculas y sin tildes. Una frase contradice un
# semáforo amarillo o rojo solo si da PERMISO y además menciona la TAREA. No cuentan las frases con
# negación ("no puedes", "todavía no") ni los consejos ("puedes hacer una siesta").
_PERMISO = re.compile(r"\b(puedes|podrias|estas (lista|listo|apta|apto)|en condiciones|sin problemas?)\b"
                      r"|(?<!mas )\badelante\b")  # "adelante", pero no "más adelante"
_NEGACION = re.compile(r"\b(no (puedes|podrias|estas|debes|deberias|conviene|se recomienda|hagas|salgas|vayas)"
                       r"|aun no|todavia no|nunca|mejor no)\b")
_CONSEJO = re.compile(r"\b(puedes|podrias)\s+((hacer|realizar|tomar|tomarte|repetir|intentar|probar)\s+)?"
                      r"((una?|la|el|otra|tu)\s+)?(siesta|descans|pausa|respir|evalua|prueba|medicion|hidrat|dorm)\w*")
_PREPARACION = re.compile(r"\bantes de (salir|ir) a\b")  # "antes de salir a la caminata, revisa..." no es permiso
_TAREA_SIEMPRE = ("caminata", "tarea", "maniobra")


def _patron_tarea(tarea: str) -> str:
    """Palabras que cuentan como "la tarea": las de siempre y las de la tarea evaluada."""
    palabras = set(_TAREA_SIEMPRE)
    palabras.update(p for p in re.findall(r"[a-z]+", _normalizar(tarea or ""))
                    if len(p) >= 4 and p not in ("para", "como", "sobre", "entre", "desde", "hacia"))
    return r"(" + "|".join(sorted(palabras)) + r")s?\b"


def _frase_contradice(frase: str, tarea: str) -> bool:
    f = _normalizar(frase)
    if not re.search(r"\b" + tarea, f) or _NEGACION.search(f):
        return False
    f = _PREPARACION.sub(" ", _CONSEJO.sub(" ", f))  # se quitan los consejos antes de buscar el permiso
    # "salir a" o "ir a" solo cuentan pegados a la tarea: "puedes salir a la caminata", "ve a hacer la tarea"
    return bool(_PERMISO.search(f) or re.search(r"\b(salir|ir) a (la |el |hacer (la |el )?)?" + tarea, f))


def quitar_contradicciones(texto: str, ev: dict | None) -> tuple[str, int]:
    """Quita las frases que dan permiso para la tarea con semáforo amarillo o rojo.

    Devuelve el texto que queda y cuántas frases se quitaron.
    """
    if not ev or ev.get("color") not in ("amarillo", "rojo"):
        return texto, 0
    patron = _patron_tarea(ev.get("tarea", ""))
    frases = [f for f in re.split(r"(?<=[.!?;])\s+", texto or "") if f.strip()]
    quedan = [f for f in frases if not _frase_contradice(f, patron)]
    return " ".join(quedan), len(frases) - len(quedan)


def contradice(texto: str, ev: dict | None) -> bool:
    """True si alguna frase da permiso para la tarea cuando el semáforo es amarillo o rojo."""
    return quitar_contradicciones(texto, ev)[1] > 0


def con_recordatorio(texto: str, fichas: list) -> str:
    """Agrega RECORDATORIO si la ficha principal es de salud y la respuesta no lo dice ya."""
    if not fichas or fichas[0].titulo not in FICHAS_DE_SALUD:
        return texto
    t = _normalizar(texto)
    if "personal capacitado" in t or "responsable medico" in t:
        return texto
    return f"{texto} {RECORDATORIO}"


def primeras_frases(texto: str, n: int = 2) -> str:
    frases = [f.strip() for f in texto.replace("\n", " ").split(". ") if f.strip()]
    frases = [f for f in frases if not f.lower().startswith("fuente")]
    return ". ".join(frases[:n]).rstrip(".") + "."


class Copiloto:
    def __init__(self, args):
        self.persona = args.persona
        self.tarea = ""
        self.tripulacion = leer_tripulacion(config.get("TRIPULACION"))
        self.evaluaciones: dict[str, dict] = {}
        self.auto = not args.sin_auto
        self._listo_para_auto = False      # evita leer en voz alta evaluaciones viejas al arrancar
        self._ultimo_id_eval: dict[str, str] = {}
        self._lock = threading.Lock()      # una respuesta a la vez
        self._escuchando = threading.Lock()  # un pedido de escuchar a la vez (botón Hablar de la estación)

        self.buscador = Buscador()
        print(f"[copiloto] {len(self.buscador.fichas)} fichas de protocolo cargadas.")
        self.llm = None if args.sin_llm else CerebroLLM()
        self.locutor = Locutor(activo=not args.sin_voz)
        self.transcriptor = None if args.texto else Transcriptor()

        self.cli = None if args.sin_mqtt else ClienteMQTT("copiloto")
        if self.cli and self.cli.conectar():
            self.cli.suscribir("apto/+/evaluacion", self._al_recibir_evaluacion)
            self.cli.suscribir("apto/control/sesion", self._al_cambiar_sesion)
            self.cli.suscribir("apto/control/pregunta", self._al_recibir_pregunta)
            self.cli.suscribir("apto/control/escuchar", self._al_pedir_escucha)
            time.sleep(0.5)  # dar tiempo a que lleguen las evaluaciones guardadas (retain)
        elif self.cli:
            print("\n" + "!" * 60)
            print("  SIN CONEXIÓN MQTT: el copiloto no recibirá evaluaciones.")
            print("  Arranquen Mosquitto en otra ventana y vuelvan a abrir el copiloto:")
            print('  & "C:\\Program Files\\mosquitto\\mosquitto.exe" -c mosquitto\\mosquitto-dev.conf -v')
            print("!" * 60 + "\n")
        threading.Timer(2.0, self._activar_auto).start()

    def _activar_auto(self):
        self._listo_para_auto = True

    # ------------------------------------------------------------ MQTT
    def _al_recibir_evaluacion(self, tema_mqtt: str, ev: dict):
        persona = ev.get("persona") or persona_de_tema(tema_mqtt)
        ev["persona"] = persona
        ident = f"{ev.get('sesion')}|{ev.get('ts')}|{ev.get('color')}"
        if self._ultimo_id_eval.get(persona) == ident:
            return  # mensaje repetido
        self._ultimo_id_eval[persona] = ident
        self.evaluaciones[persona] = ev
        print(f"[copiloto] Nueva evaluación de {persona}: {ev.get('color')}")
        if self.auto and self._listo_para_auto and persona == self.persona:
            texto = resumen(ev, self.tarea)
            self.locutor.decir(texto)
            self._publicar(persona, "(resumen automático)", texto, [], "resumen", "auto")

    def _al_cambiar_sesion(self, _tema: str, datos: dict):
        antes = (self.persona, self.tarea)
        if datos.get("persona"):
            self.persona = datos["persona"]
        if "tarea" in datos:
            self.tarea = datos.get("tarea") or ""
        if (self.persona, self.tarea) != antes:  # el mensaje propio de _cambiar_persona no se repite
            print(f"[copiloto] Persona activa: {self.persona}  Tarea: {self.tarea or '-'}")

    def _cambiar_persona(self, persona: str):
        """Cambia la persona activa y lo avisa a todos en apto/control/sesion, con la tarea actual."""
        anterior = self.evaluaciones.get(self.persona) or self.evaluaciones.get(persona) or {}
        tarea = self.tarea or anterior.get("tarea") or ""
        self.persona, self.tarea = persona, tarea
        print(f"[copiloto] Persona activa: {persona}  Tarea: {tarea or '-'}")
        if self.cli:
            # con retain, como la estación: el ESP32 sabe la persona activa aunque se reinicie
            self.cli.publicar("apto/control/sesion", {"persona": persona, "tarea": tarea}, retener=True)

    def _al_recibir_pregunta(self, _tema: str, datos: dict):
        pregunta = (datos.get("pregunta") or "").strip()
        if pregunta:
            persona = datos.get("persona") or self.persona
            threading.Thread(target=self.responder, args=(pregunta, "panel", persona), daemon=True).start()

    def _al_pedir_escucha(self, _tema: str, datos: dict):
        """Botón Hablar de la estación: escuchar con el micrófono de esta laptop, transcribir y responder."""
        persona = datos.get("persona") or self.persona
        threading.Thread(target=self._escuchar_panel, args=(persona, datos), daemon=True).start()

    def _escuchar_panel(self, persona: str, datos: dict):
        def estado(valor: str, **extra):
            if self.cli:
                self.cli.publicar("apto/control/estado_escucha", {"persona": persona, "estado": valor, **extra})

        if not self.transcriptor:
            estado("error", motivo="El copiloto está abierto en modo texto (--texto): no puede escuchar.")
            return
        if not self._escuchando.acquire(blocking=False):
            estado("error", motivo="Ya estoy escuchando otra pregunta.")
            return
        try:
            self.locutor.esperar()  # que no se grabe su propia voz
            estado("escuchando")
            print("   [panel] Escuchando una pregunta por el micrófono...")
            marca = datetime.now().strftime("%Y%m%d-%H%M%S")
            ruta = grabar_hasta_silencio(CARPETA_AUDIO / f"{marca}-panel.wav",
                                         max_s=float(datos.get("segundos_max") or 10))
            if not ruta:
                estado("error", motivo="No escuché nada. Acércate al micrófono e intenta de nuevo.")
                return
            estado("transcribiendo")
            t0 = time.time()
            pregunta = self.transcriptor.transcribir(ruta)
            print(f"   [Whisper {time.time() - t0:.1f} s] Escuché: «{pregunta}»")
            if not pregunta:
                estado("error", motivo="No entendí la pregunta. Intenta de nuevo, más cerca del micrófono.")
                return
            estado("listo", texto=pregunta)
            self.responder(pregunta, "voz-panel", persona)
        except Exception as e:  # micrófono ocupado o sin permiso, etc.
            estado("error", motivo=f"No se pudo escuchar ({e}).")
        finally:
            self._escuchando.release()

    def _publicar(self, persona, pregunta, respuesta, fichas, modo, origen):
        if self.cli:
            self.cli.publicar(tema(persona, "copiloto"), {
                "persona": persona, "pregunta": pregunta, "respuesta": respuesta,
                "fichas": fichas, "modo": modo, "origen": origen,
            })

    # ------------------------------------------------------------ responder
    def responder(self, pregunta: str, origen: str = "local", persona: str | None = None) -> str:
        with self._lock:
            persona = persona or self.persona
            original = pregunta
            ident = identificar(pregunta, self.tripulacion)
            if ident:
                quien, resto = ident
                if quien:
                    self._cambiar_persona(quien)
                    persona = quien
                    if not resto:  # solo «soy Eric»: se saluda y no se sigue
                        return self._decir_y_publicar(persona, original, self._saludo(quien), [], "identificacion", origen)
                    pregunta = resto  # «Soy Eric, me falta el aire»: se responde el resto como Eric
                elif not resto:  # «soy Diego»: nombre que no es de la tripulación
                    nombres = _lista([p.capitalize() for p in self.tripulacion])
                    return self._decir_y_publicar(persona, original,
                                                  f"No reconozco ese nombre. La tripulación es: {nombres}.",
                                                  [], "identificacion", origen)
                # Nombre desconocido con más texto ("habla más despacio"): no era una identificación.
            ev = self.evaluaciones.get(persona)
            alarma = es_alarma(pregunta)
            # primero las fichas de la pregunta; si pregunta por su resultado, también las de sus motivos
            fichas = self.buscador.buscar(pregunta, k=2)
            if ev and pregunta_sobre_resultado(pregunta) and not alarma:
                contexto = ev.get("color", "") + " " + " ".join(ev.get("motivos") or [])
                for f in self.buscador.buscar(contexto, k=2):
                    if f not in fichas:
                        fichas.append(f)
            fichas = fichas[:3]

            t0 = time.time()
            modo = "fichas"
            usar_llm = bool(self.llm and self.llm.disponible)
            try:
                if alarma:
                    # Síntoma de alarma: va antes que todo y no usa el modelo.
                    texto, modo = respuesta_alarma(fichas), "alarma"
                elif pregunta_sobre_tripulacion(pregunta):
                    # ¿Quién está más apto? Respuesta fija con las evaluaciones de todos.
                    texto = resumen_tripulacion(self.evaluaciones, (ev or {}).get("tarea") or self.tarea, persona)
                    modo = "tripulacion"
                elif not ev and pregunta_sobre_resultado(pregunta):
                    texto = ("Todavía no tengo una evaluación tuya. Para saber si estás apta o apto, haz una "
                             "evaluación de unos 5 minutos: el sensor en el dedo, un minuto frente a la cámara, "
                             "la frase en voz alta y la prueba de reacción de 3 minutos.")
                    modo = "sin evaluacion"
                elif ev and pregunta_sobre_resultado(pregunta):
                    texto, modo = self._respuesta_resultado(pregunta, ev, persona, fichas, usar_llm)
                elif usar_llm:
                    texto = self.llm.responder(pregunta, ev, fichas)  # máximo 3 frases
                    modo = "llm"
                    limpio, quitadas = quitar_contradicciones(texto, ev)
                    if quitadas and limpio:
                        # Solo se quitan las frases que contradicen la evaluación; el resto se conserva.
                        print(f"   [aviso] Se quitaron {quitadas} frase(s) que contradecían la evaluación.")
                        texto, modo = limpio, "llm (corregido)"
                    elif quitadas:
                        print("   [aviso] El modelo contradijo la evaluación; uso la respuesta fija.")
                        texto = self._respuesta_sin_llm(pregunta, ev, fichas, forzar_resumen=True)
                        modo = "fichas (corregido)"
                else:
                    texto = self._respuesta_sin_llm(pregunta, ev, fichas)
            except Exception as e:
                print(f"[copiloto] Falló el modelo de lenguaje ({e}); respondo con las fichas.")
                texto = self._respuesta_sin_llm(pregunta, ev, fichas)
                modo = "fichas"
                if alarma:  # pase lo que pase, ante una alarma se dicen la medida, el aviso y la advertencia
                    texto, modo = f"{MEDIDA_SIN_FICHA} {AVISO} {ADVERTENCIA}", "alarma"
            if modo in ("llm", "llm (corregido)", "fichas", "fichas (corregido)"):
                # Consejos del modelo o de las fichas: recordatorio fijo, aparte de las 3 frases del modelo.
                # La alarma ya trae su ADVERTENCIA, y los resúmenes fijos no lo necesitan.
                texto = con_recordatorio(texto, fichas)
            print(f"   [{modo}, {time.time() - t0:.1f} s, fichas: {', '.join(f.titulo for f in fichas) or 'ninguna'}]")
            return self._decir_y_publicar(persona, original, texto, [f.titulo for f in fichas], modo, origen,
                                          imprimir_modo=False)

    def _decir_y_publicar(self, persona, pregunta, texto, fichas, modo, origen, imprimir_modo=True) -> str:
        if imprimir_modo:
            print(f"   [{modo}, 0.0 s, fichas: {', '.join(fichas) or 'ninguna'}]")
        self.locutor.decir(texto)
        self._publicar(persona, pregunta, texto, fichas, modo, origen)
        return texto

    def _saludo(self, persona: str) -> str:
        """«Hola Eric.» y su último color, si tiene evaluación (los detalles, solo si los pide)."""
        texto = f"Hola {persona.capitalize()}."
        ev = self.evaluaciones.get(persona)
        if ev and ev.get("color"):
            return f"{texto} Tu último resultado es {ev['color']}. Pregúntame si quieres los detalles."
        return f"{texto} Todavía no tienes una evaluación."

    def _complemento(self, ya_dicho: str, pregunta: str, ev: dict | None, fichas: list) -> str:
        """Una frase del modelo para agregar a un texto fijo; se descarta si contradice la evaluación."""
        frase = self.llm.complementar(ya_dicho, pregunta, fichas)
        if contradice(frase, ev):
            print("   [aviso] La frase del modelo contradecía la evaluación; se descarta.")
            return ""
        return frase

    def _respuesta_resultado(self, pregunta: str, ev: dict, persona: str, fichas: list,
                             usar_llm: bool) -> tuple[str, str]:
        """Sobre su propio resultado: el resumen fijo (nunca contradice la evaluación) y una frase más."""
        texto, modo = resumen(ev, self.tarea), "resumen"
        verde = mejor_en_verde(self.evaluaciones, persona) if ev.get("color") in ("amarillo", "rojo") else None
        if verde:
            # Quién podría hacerla en su lugar. Sin frase del modelo, para no alargar.
            texto += f" {(verde.get('persona') or '').capitalize()} está en verde y podría hacer la tarea en tu lugar."
        elif usar_llm:
            extra = self._complemento(texto, pregunta, ev, fichas)
            if extra:
                texto += " " + extra
                modo = "resumen+llm"
        elif fichas:
            texto += " " + primeras_frases(fichas[0].texto, 1)
        return texto, modo

    def _respuesta_sin_llm(self, pregunta: str, ev: dict | None, fichas: list,
                           forzar_resumen: bool = False) -> str:
        partes = []
        if ev and (forzar_resumen or pregunta_sobre_resultado(pregunta)):
            partes.append(resumen(ev, self.tarea))
        if fichas:
            # con el resumen delante basta una frase de la ficha, para no alargar la respuesta
            partes.append(primeras_frases(fichas[0].texto, 1 if partes else 2))
        if not partes:
            partes.append("No tengo información para responder eso. Consulta al responsable médico de la "
                          "tripulación y, si hay comunicación, al médico de vuelo en Tierra.")
        return " ".join(partes)

    # ------------------------------------------------------------ voz
    def escuchar_y_responder(self):
        if not self.transcriptor:
            print("   (Modo texto: escribe tu pregunta.)")
            return
        marca = datetime.now().strftime("%Y%m%d-%H%M%S")
        ruta = grabar_hasta_enter(CARPETA_AUDIO / f"{marca}.wav")
        if not ruta:
            print("   No se escuchó nada. Intenta de nuevo.")
            return
        t0 = time.time()
        pregunta = self.transcriptor.transcribir(ruta)
        print(f"   [Whisper {time.time() - t0:.1f} s] Escuché: «{pregunta}»")
        if pregunta:
            self.responder(pregunta, "voz")
        else:
            print("   No entendí la pregunta. Intenta de nuevo, más cerca del micrófono.")


def main():
    ap = argparse.ArgumentParser(description="Copiloto por voz de «¿Está apto hoy?»")
    ap.add_argument("--persona", default=config.get("PERSONA", "bri"))
    ap.add_argument("--texto", action="store_true", help="preguntas escritas; no carga Whisper")
    ap.add_argument("--sin-voz", action="store_true", help="no habla; solo muestra el texto")
    ap.add_argument("--sin-llm", action="store_true", help="no usa Ollama; responde con las fichas")
    ap.add_argument("--sin-mqtt", action="store_true", help="no conecta a MQTT")
    ap.add_argument("--sin-auto", action="store_true", help="no lee en voz alta cada evaluación nueva")
    args = ap.parse_args()

    cop = Copiloto(args)
    if cop.llm and cop.llm.disponible:
        # Se carga ANTES de la primera pregunta: en frío puede tardar hasta un minuto.
        print(f"[copiloto] Cargando {cop.llm.modelo} (la primera vez puede tardar hasta un minuto)...")
        try:
            print(f"[copiloto] Modelo listo en {cop.llm.precalentar():.1f} s")
        except Exception as e:
            print(f"[copiloto] No se pudo cargar el modelo ({e}); se responderá con las fichas.")
            cop.llm.disponible = False
    if cop.transcriptor:
        cop.transcriptor.cargar()

    print("""
==================== COPILOTO ====================
  Enter vacío      hablar por el micrófono
  escribir + Enter pregunta escrita
  r                repetir el resumen de la última evaluación
  p nombre         cambiar la persona activa
  q                salir
==================================================""")
    while True:
        try:
            linea = input(f"[{cop.persona}] > ").lstrip("﻿").strip()  # ﻿: BOM de PowerShell
        except (EOFError, KeyboardInterrupt):
            break
        if linea.lower() in ("q", "salir"):
            break
        if linea == "":
            cop.escuchar_y_responder()
        elif linea.lower() == "r":
            ev = cop.evaluaciones.get(cop.persona)
            cop.locutor.decir(resumen(ev, cop.tarea) if ev else "Todavía no hay una evaluación para esta persona.")
        elif linea.lower().startswith("p "):
            cop.persona = linea[2:].strip().lower()
            print(f"   Persona activa: {cop.persona}")
        else:
            cop.responder(linea)
        cop.locutor.esperar()
    if cop.cli:
        cop.cli.cerrar()


if __name__ == "__main__":
    main()
