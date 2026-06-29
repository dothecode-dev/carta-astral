"""Normalización de texto para geocoding.

La MISMA función se usa en import-time (al construir los tokens de GeoNames) y
en request-time (al tokenizar la query del usuario). Si divergen, los tokens
persistidos dejan de matchear lo que se busca.
"""

from unidecode import unidecode


def normalize(s: str) -> str:
    """Translitera a ASCII, pasa a minúsculas y colapsa espacios.

    unidecode resuelve el latino-extendido que NFKD no toca (ø→o, ł→l, ß→ss).
    """
    return " ".join(unidecode(s).lower().split())


def tokenize(s: str) -> list[str]:
    """Parte el texto normalizado en palabras, descartando tokens vacíos."""
    return [t for t in normalize(s).split(" ") if t]
