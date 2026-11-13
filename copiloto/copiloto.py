"""Copiloto por voz de «¿Está apto hoy?».

- Escucha las evaluaciones del coordinador (apto/+/evaluacion) y explica el semáforo en voz alta.
- Responde preguntas habladas o escritas usando SOLO las fichas de protocolo y la evaluación actual.
- Publica cada respuesta en apto/{persona}/copiloto para que el resto del equipo la vea en la interfaz.

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
"""
import argparse
import re
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # para importar comun/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from buscador import Buscador
from habla import Locutor, Transcriptor, grabar_hasta_enter
from llm import CerebroLLM

from comun import config
from comun.mqtt_cliente import ClienteMQTT, persona_de_tema, tema

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


def pregunta_sobre_resultado(pregunta: str) -> bool:
    return any(p in pregunta.lower() for p in PALABRAS_RESULTADO)


def pregunta_sobre_tripulacion(pregunta: str) -> bool:
    return any(p in pregunta.lower() for p in PALABRAS_TRIPULACION)


def _nombres(evs: list[dict]) -> str:
    nombres = [(e.get("persona") or "").capitalize() for e in evs]
    return nombres[0] if len(nombres) == 1 else ", ".join(nombres[:-1]) + " y " + nombres[-1]


def resumen_tripulacion(evaluaciones: dict[str, dict], tarea: str = "") -> str:
    """Quién está más apto para la tarea, según las evaluaciones recibidas (respuesta fija)."""
    evs = [e for e in evaluaciones.values() if e.get("color") in ORDEN_COLOR]
    if not evs:
        return ("Todavía no hay evaluaciones de la tripulación. Cada persona debe hacer su evaluación "
                "para que pueda recomendar quién hace la tarea.")
    evs.sort(key=lambda e: (ORDEN_COLOR[e["color"]], -float(e.get("puntaje") or 0)))
    para = f" para la {tarea}" if tarea else ""
    verdes = [e for e in evs if e["color"] == "verde"]
    amarillos = [e for e in evs if e["color"] == "amarillo"]
    rojos = [e for e in evs if e["color"] == "rojo"]
    partes = []
    if verdes:
        partes.append(f"La persona más apta{para} es {verdes[0]['persona'].capitalize()}, en verde.")
        if len(verdes) > 1:
            partes.append(f"También están en verde: {_nombres(verdes[1:])}.")
    else:
        partes.append(f"Nadie está en verde{para}. La opción menos riesgosa es "
                      f"{evs[0]['persona'].capitalize()}, en {evs[0]['color']}: conviene hacerla en pareja o posponerla.")
    resto = [f"{_nombres(amarillos)} en amarillo" if amarillos and verdes else "",
             f"{_nombres(rojos)} en rojo" if rojos else ""]
    resto = [r for r in resto if r]
    if resto:
        partes.append("Están " + " y ".join(resto) + ".")
    if len(evs) == 1:
        partes.append("Solo tengo la evaluación de una persona; faltan las demás.")
    return " ".join(partes)


def resumen(ev: dict, tarea_activa: str = "") -> str:
    """Explicación corta y fija del semáforo (no usa el modelo de lenguaje: es instantánea)."""
    nombre = (ev.get("persona") or "").capitalize()
    color = ev.get("color", "sin color")
    tarea = ev.get("tarea") or tarea_activa
    partes = [f"{nombre}, tu resultado{' para ' + tarea if tarea else ''} es {color}."]
    if ev.get("motivos"):
        partes.append(f"Motivos: {_unir(ev['motivos'])}.")
    elif color == "verde":
        partes.append("Tus señales están en tu rango habitual.")
    if ev.get("accion"):
        partes.append(f"Recomendación: {ev['accion'].rstrip('.')}.")
    return " ".join(partes)


_PERMISO = re.compile(r"\b(puedes|podrías|podrias|estás apto|estas apto)\s+(realizar|hacer|llevar a cabo|continuar|para)\b",
                      re.IGNORECASE)


def contradice(texto: str, ev: dict | None) -> bool:
    """True si el modelo da permiso para la tarea cuando el semáforo es amarillo o rojo."""
    if not ev or ev.get("color") not in ("amarillo", "rojo"):
        return False
    return bool(_PERMISO.search(texto))


def primeras_frases(texto: str, n: int = 2) -> str:
    frases = [f.strip() for f in texto.replace("\n", " ").split(". ") if f.strip()]
    frases = [f for f in frases if not f.lower().startswith("fuente")]
    return ". ".join(frases[:n]).rstrip(".") + "."


class Copiloto:
    def __init__(self, args):
        self.persona = args.persona
        self.tarea = ""
        self.evaluaciones: dict[str, dict] = {}
        self.auto = not args.sin_auto
        self._listo_para_auto = False      # evita leer en voz alta evaluaciones viejas al arrancar
        self._ultimo_id_eval: dict[str, str] = {}
        self._lock = threading.Lock()      # una respuesta a la vez

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
        if datos.get("persona"):
            self.persona = datos["persona"]
        if "tarea" in datos:
            self.tarea = datos.get("tarea") or ""
        print(f"[copiloto] Persona activa: {self.persona}  Tarea: {self.tarea or '-'}")

    def _al_recibir_pregunta(self, _tema: str, datos: dict):
        pregunta = (datos.get("pregunta") or "").strip()
        if pregunta:
            persona = datos.get("persona") or self.persona
            threading.Thread(target=self.responder, args=(pregunta, "panel", persona), daemon=True).start()

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
            ev = self.evaluaciones.get(persona)
            # primero las fichas de la pregunta; si pregunta por su resultado, también las de sus motivos
            fichas = self.buscador.buscar(pregunta, k=2)
            if ev and pregunta_sobre_resultado(pregunta):
                contexto = ev.get("color", "") + " " + " ".join(ev.get("motivos") or [])
                for f in self.buscador.buscar(contexto, k=2):
                    if f not in fichas:
                        fichas.append(f)
            fichas = fichas[:3]

            t0 = time.time()
            modo = "fichas"
            usar_llm = bool(self.llm and self.llm.disponible)
            try:
                if pregunta_sobre_tripulacion(pregunta):
                    # ¿Quién está más apto? Respuesta fija con las evaluaciones de todos.
                    texto = resumen_tripulacion(self.evaluaciones, (ev or {}).get("tarea") or self.tarea)
                    modo = "tripulacion"
                elif not ev and pregunta_sobre_resultado(pregunta):
                    texto = ("Todavía no tengo una evaluación tuya. Para saber si estás apta o apto, haz una "
                             "evaluación de unos 5 minutos: el sensor en el dedo, un minuto frente a la cámara, "
                             "la frase en voz alta y la prueba de reacción de 3 minutos.")
                    modo = "sin evaluacion"
                elif ev and pregunta_sobre_resultado(pregunta):
                    # Sobre su resultado: el resumen fijo (nunca contradice la evaluación)
                    # más una frase de consejo del modelo.
                    texto = resumen(ev, self.tarea)
                    if usar_llm:
                        texto += " " + self.llm.complementar(texto, pregunta, fichas)
                        modo = "resumen+llm"
                    elif fichas:
                        texto += " " + primeras_frases(fichas[0].texto, 1)
                elif usar_llm:
                    texto = self.llm.responder(pregunta, ev, fichas)
                    modo = "llm"
                    if contradice(texto, ev):
                        print("   [aviso] El modelo contradijo la evaluación; uso la respuesta fija.")
                        texto = self._respuesta_sin_llm(pregunta, ev, fichas, forzar_resumen=True)
                        modo = "fichas (corregido)"
                else:
                    texto = self._respuesta_sin_llm(pregunta, ev, fichas)
            except Exception as e:
                print(f"[copiloto] Falló el modelo de lenguaje ({e}); respondo con las fichas.")
                texto = self._respuesta_sin_llm(pregunta, ev, fichas)
                modo = "fichas"
            print(f"   [{modo}, {time.time() - t0:.1f} s, fichas: {', '.join(f.titulo for f in fichas) or 'ninguna'}]")

            self.locutor.decir(texto)
            self._publicar(persona, pregunta, texto, [f.titulo for f in fichas], modo, origen)
            return texto

    def _respuesta_sin_llm(self, pregunta: str, ev: dict | None, fichas: list,
                           forzar_resumen: bool = False) -> str:
        partes = []
        if ev and (forzar_resumen or pregunta_sobre_resultado(pregunta)):
            partes.append(resumen(ev, self.tarea))
        if fichas:
            # con el resumen delante basta una frase de la ficha, para no alargar la respuesta
            partes.append(primeras_frases(fichas[0].texto, 1 if partes else 2))
        if not partes:
            partes.append("No tengo información para responder eso. Consulta al médico de vuelo.")
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
    ap.add_argument("--persona", default=config.get("PERSONA", "xone"))
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
