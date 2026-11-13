"""Busca las fichas de protocolo más relevantes para una pregunta (BM25, sin internet)."""
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

ARCHIVO = Path(__file__).resolve().parent / "protocolos.md"

_STOP = set("""
a al algo como con contra cual cuando de del desde donde el ella ellas ellos en entre era es esa ese eso esta
este esto estoy fue ha hay la las le les lo los mas me mi mis muy ni no nos o os para pero por que se segun
si sin sobre su sus te ti tu tus un una uno unos unas y ya yo hoy puedo puede debo deberia tengo tiene estas
esta estan qué cómo por porque cuanto cuanta
""".split())


def _normalizar(texto: str) -> list[str]:
    texto = unicodedata.normalize("NFD", texto.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")  # quita tildes
    palabras = re.findall(r"[a-z0-9]+", texto)
    # "raíz" simple: las primeras 5 letras (dormí, dormir, dormido -> dormi)
    return [p[:5] for p in palabras if p not in _STOP and len(p) > 1]


@dataclass
class Ficha:
    titulo: str
    texto: str          # lo que se dice o se pasa al modelo (sin claves ni fuente)
    claves: str = ""    # solo para buscar
    fuente: str = ""    # para mostrar en la interfaz, no se lee en voz alta

    @property
    def id(self) -> str:
        return "-".join(_normalizar(self.titulo)) or "ficha"


def cargar_fichas(ruta: Path = ARCHIVO) -> list[Ficha]:
    contenido = re.sub(r"<!--.*?-->", "", ruta.read_text(encoding="utf-8"), flags=re.S)
    fichas = []
    for bloque in re.split(r"^## ", contenido, flags=re.M)[1:]:
        lineas = bloque.strip().splitlines()
        claves, fuente, cuerpo = "", "", []
        for linea in lineas[1:]:
            if linea.lower().startswith("claves:"):
                claves = linea.split(":", 1)[1].strip()
            elif linea.lower().startswith("fuente:"):
                fuente = linea.split(":", 1)[1].strip()
            else:
                cuerpo.append(linea)
        fichas.append(Ficha(lineas[0].strip(), "\n".join(cuerpo).strip(), claves, fuente))
    return fichas


class Buscador:
    def __init__(self, ruta: Path = ARCHIVO):
        self.fichas = cargar_fichas(ruta)
        # el título y las claves cuentan doble
        corpus = [(_normalizar(f.titulo) + _normalizar(f.claves)) * 2 + _normalizar(f.texto)
                  for f in self.fichas]
        self._bm25 = BM25Okapi(corpus)

    def buscar(self, consulta: str, k: int = 3) -> list[Ficha]:
        tokens = _normalizar(consulta)
        if not tokens:
            return []
        puntajes = self._bm25.get_scores(tokens)
        orden = sorted(range(len(self.fichas)), key=lambda i: puntajes[i], reverse=True)
        return [self.fichas[i] for i in orden[:k] if puntajes[i] > 0]

    def por_titulo(self, titulo: str) -> Ficha | None:
        for f in self.fichas:
            if f.titulo.lower() == titulo.lower():
                return f
        return None


if __name__ == "__main__":  # prueba rápida: python copiloto/buscador.py "dormí poco"
    import sys
    b = Buscador()
    pregunta = " ".join(sys.argv[1:]) or "dormí muy poco, ¿puedo hacer la caminata espacial?"
    print(f"Pregunta: {pregunta}\n")
    for f in b.buscar(pregunta):
        print(f"- {f.titulo}")
