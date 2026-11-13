"""Respuestas del copiloto con un modelo local de Ollama (sin internet).

Si Ollama no está disponible, el copiloto usa respuestas armadas con las fichas (modo sin LLM).
"""
import re
import time

from comun import config

SISTEMA = """Eres el copiloto de salud de una tripulación espacial, dentro del prototipo «¿Está apto hoy?».
Tu respuesta se lee en voz alta: respondes en español, en un máximo de 3 frases cortas, con tono claro y tranquilo.
Usa SOLO la evaluación actual y las fichas de protocolo que recibes en el mensaje.
Reglas:
1. Nunca contradigas la evaluación. Si el color es amarillo o rojo, nunca digas que la persona puede hacer la tarea sin condiciones: menciona sus motivos y la acción recomendada.
2. Nunca diagnostiques enfermedades ni recomiendes medicamentos.
3. Si la información recibida no alcanza para responder, dilo y sugiere consultar al médico de vuelo.
4. No inventes números ni datos que no estén en el mensaje.
5. Ante dolor de pecho, falta de aire, mareo o confusión, indica avisar de inmediato al comandante y al médico de vuelo.
6. Habla directo a la persona. No menciones las fichas, la guía ni «según la evaluación».
7. Sin listas, sin markdown y sin emojis."""


def describir_evaluacion(ev: dict | None) -> str:
    """La evaluación en palabras simples (al modelo le cuesta menos que un JSON)."""
    if not ev:
        return "Todavía no hay una evaluación para esta persona."
    partes = [f"Color del semáforo: {ev.get('color', 'desconocido')}."]
    if ev.get("tarea"):
        partes.append(f"Tarea evaluada: {ev['tarea']}.")
    if ev.get("motivos"):
        partes.append("Motivos: " + "; ".join(ev["motivos"]) + ".")
    if ev.get("accion"):
        partes.append(f"Acción recomendada: {ev['accion']}.")
    return " ".join(partes)


class CerebroLLM:
    def __init__(self):
        self.modelo = config.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.disponible = False
        self._ollama = None
        try:
            import ollama
            ollama.show(self.modelo)  # falla si Ollama no corre o el modelo no está descargado
            self._ollama = ollama
            self.disponible = True
        except Exception as e:
            print(f"[copiloto] Ollama no disponible ({e.__class__.__name__}): se usarán respuestas sin LLM.")

    def precalentar(self) -> float:
        """Carga el modelo en la tarjeta gráfica y lo deja cargado (keep_alive=-1). Devuelve los segundos."""
        if not self.disponible:
            return 0.0
        t0 = time.time()
        self._chat("Eres un asistente.", "Responde solo: listo", num_predict=3)
        return time.time() - t0

    def _chat(self, sistema: str, usuario: str, num_predict: int) -> str:
        r = self._ollama.chat(
            model=self.modelo,
            messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
            options={"temperature": 0.2, "num_predict": num_predict, "num_ctx": 4096},
            keep_alive=-1,
        )
        return limpiar(r["message"]["content"])

    def responder(self, pregunta: str, evaluacion: dict | None, fichas: list) -> str:
        contexto_fichas = "\n\n".join(f"[{f.titulo}]\n{f.texto}" for f in fichas) or "Ninguna ficha relevante."
        usuario = (
            f"EVALUACIÓN ACTUAL: {describir_evaluacion(evaluacion)}\n\n"
            f"FICHAS DE PROTOCOLO:\n{contexto_fichas}\n\n"
            f"PREGUNTA DEL ASTRONAUTA: {pregunta}"
        )
        return limitar_frases(self._chat(SISTEMA, usuario, 160), 3)

    def complementar(self, ya_dicho: str, pregunta: str, fichas: list) -> str:
        """Una sola frase con un consejo práctico, para agregar después del resumen fijo."""
        contexto_fichas = "\n\n".join(f"[{f.titulo}]\n{f.texto}" for f in fichas) or "Ninguna ficha relevante."
        usuario = (
            f"YA SE LE DIJO A LA PERSONA: {ya_dicho}\n\n"
            f"FICHAS DE PROTOCOLO:\n{contexto_fichas}\n\n"
            f"PREGUNTA DEL ASTRONAUTA: {pregunta}\n\n"
            "Agrega UNA sola frase con un consejo práctico de las fichas que le ayude con esos motivos. "
            "No repitas el resultado, los motivos ni la recomendación, y no digas que puede hacer la tarea."
        )
        return limitar_frases(self._chat(SISTEMA, usuario, 70), 1)


def limpiar(texto: str) -> str:
    """Quita markdown y saltos para que se lea bien en voz alta."""
    texto = re.sub(r"[*_#`>]+", "", texto)
    texto = re.sub(r"^\s*[-•]\s*", "", texto, flags=re.M)
    texto = re.sub(r"\s[-•]\s", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def limitar_frases(texto: str, maximo: int) -> str:
    """Corta el texto a un máximo de frases (para que no se alargue al leerlo en voz alta)."""
    frases = re.split(r"(?<=[.!?])\s+", texto.strip())
    frases = [f for f in frases if f]
    return " ".join(frases[:maximo]) if frases else texto
