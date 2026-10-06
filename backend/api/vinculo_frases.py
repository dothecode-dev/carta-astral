"""Las frases fijas de la vista previa de Vínculo.

Son contenido revisado a mano, no texto generado por visita: la vista previa
es gratis y abierta, y no puede costar una llamada al modelo (RF27). Una frase
por par de planetas personales y aspecto mayor, genérica respecto del tipo de
vínculo: lo específico del tipo es parte de lo que se paga.
"""

import json
import pathlib

PERSONALES: tuple[str, ...] = ("Sun", "Moon", "Mercury", "Venus", "Mars")

_RUTA = pathlib.Path(__file__).parent / "data" / "vinculo_frases.json"
_FRASES: dict[str, dict[str, str]] = json.loads(_RUTA.read_text(encoding="utf-8"))


def clave(p1: str, p2: str, aspecto: str) -> str:
    a, b = sorted((p1, p2), key=PERSONALES.index)
    return f"{a}|{b}|{aspecto}"


def frase(p1: str, p2: str, aspecto: str, lang: str) -> str:
    return _FRASES[lang][clave(p1, p2, aspecto)]
