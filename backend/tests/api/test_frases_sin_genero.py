"""Las frases fijas de la firma y de Vínculo no marcan el género del lector (RF5b).

Son texto versionado que se le muestra a cualquiera, elija el trato que elija:
tienen que estar en neutro. El test recorre todas las frases en español y en
portugués y falla si alguna contiene, como palabra entera y sin distinguir
mayúsculas, un adjetivo de la lista cerrada de la medición del 07-10.

Algunas coincidencias no marcan el género de la persona («solo» adverbio, un
adjetivo que es de la relación y no de quien lee). Esas van a LISTA_BLANCA, una
por una, con el motivo: la excepción es de la frase, no de la palabra, para que
una frase nueva con la misma palabra vuelva a fallar y se revise a mano.
"""

import json
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[2] / "api" / "data"
ARCHIVOS = ("firma_frases.json", "vinculo_frases.json")
IDIOMAS = ("es", "pt")

PALABRAS = (
    "vos misma", "vos mismo", "você mesma", "você mesmo",
    "seguro", "segura", "solo", "sola",
    "atento", "atenta", "cuidadoso", "cuidadosa",
    "tranquilo", "tranquila", "cansado", "cansada",
    "dispuesto", "dispuesta", "preparado", "preparada",
    "obligado", "obligada", "callado", "callada",
    "cerrado", "cerrada", "querido", "querida",
    "protegido", "protegida", "sozinho", "sozinha",
    "pronto", "pronta", "prolijo", "prolija",
    "discreto", "discreta",
)
_PATRON = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(p) for p in PALABRAS) + r")(?!\w)",
    re.IGNORECASE,
)

# (archivo, idioma, clave, palabra) -> por qué esa coincidencia no marca género.
LISTA_BLANCA: dict[tuple[str, str, str, str], str] = {
    # Concuerda con «la primera impresión», no con quien lee.
    ("firma_frases.json", "es", "Ascendant|Can", "atenta"): "adjetivo de «impresión»",
    ("firma_frases.json", "pt", "Ascendant|Can", "atenta"): "adjetivo de «impressão»",
    # Es el apoyo el que es tranquilo, no una de las personas.
    ("vinculo_frases.json", "es", "Sun|Moon|sextile", "tranquilo"): "adjetivo de «apoyo»",
    ("vinculo_frases.json", "pt", "Sun|Moon|sextile", "tranquilo"): "adjetivo de «apoio»",
    # «Un lugar seguro»: el adjetivo es del lugar (el vínculo).
    ("vinculo_frases.json", "es", "Moon|Moon|trine", "seguro"): "adjetivo de «lugar»",
    ("vinculo_frases.json", "pt", "Moon|Moon|trine", "seguro"): "adjetivo de «lugar»",
    # «Una sola mirada»: el adjetivo es de la mirada.
    ("vinculo_frases.json", "es", "Mercury|Mercury|opposition", "sola"): "adjetivo de «mirada»",
    # «Ninguém segura»: verbo «segurar» (nadie lo sostiene), no adjetivo.
    ("vinculo_frases.json", "pt", "Moon|Moon|conjunction", "segura"): "verbo «segurar»",
}


def _frases():
    for archivo in ARCHIVOS:
        datos = json.loads((DATA / archivo).read_text(encoding="utf-8"))
        for lang in IDIOMAS:
            for clave, texto in datos[lang].items():
                yield archivo, lang, clave, texto


def _fallas():
    fallas = []
    for archivo, lang, clave, texto in _frases():
        for m in _PATRON.finditer(texto):
            palabra = m.group(1).lower()
            if (archivo, lang, clave, palabra) in LISTA_BLANCA:
                continue
            fallas.append(f"{archivo} [{lang}] {clave} «{palabra}»: {texto}")
    return fallas


def test_ninguna_frase_fija_marca_el_genero():
    fallas = _fallas()
    assert not fallas, f"{len(fallas)} frases marcan el género:\n" + "\n".join(fallas)


@pytest.mark.parametrize("entrada", sorted(LISTA_BLANCA))
def test_la_lista_blanca_no_tiene_entradas_muertas(entrada):
    """Si la frase cambió y ya no tiene la palabra, la excepción sobra."""
    archivo, lang, clave, palabra = entrada
    datos = json.loads((DATA / archivo).read_text(encoding="utf-8"))
    texto = datos[lang][clave]
    assert any(m.group(1).lower() == palabra for m in _PATRON.finditer(texto)), entrada
