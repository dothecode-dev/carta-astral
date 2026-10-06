"""Las frases fijas de la vista previa de Vínculo (RF28).

Son contenido versionado: una frase por par de planetas personales y aspecto
mayor, en cada idioma. Que falte una sería un 500 en la vista previa pública
para quien tenga justo ese aspecto, así que la tabla se prueba completa.
"""

import itertools

import pytest

from api.vinculo_frases import PERSONALES, clave, frase
from core.sinastria import ASPECTOS

IDIOMAS = ("es", "en", "pt")
PARES = list(itertools.combinations_with_replacement(PERSONALES, 2))


def test_son_quince_pares():
    assert len(PARES) == 15


@pytest.mark.parametrize("lang", IDIOMAS)
def test_hay_frase_para_cada_combinacion(lang):
    for (p1, p2), asp in itertools.product(PARES, ASPECTOS):
        texto = frase(p1, p2, asp, lang)
        assert texto.strip(), (p1, p2, asp, lang)


def test_la_clave_no_depende_del_orden():
    assert clave("Moon", "Sun", "trine") == clave("Sun", "Moon", "trine") == "Sun|Moon|trine"


def test_no_hay_claves_de_sobra():
    from api.vinculo_frases import _FRASES

    esperadas = {clave(p1, p2, a) for (p1, p2), a in itertools.product(PARES, ASPECTOS)}
    assert set(_FRASES) == set(IDIOMAS)
    for lang in IDIOMAS:
        assert set(_FRASES[lang]) == esperadas, lang
