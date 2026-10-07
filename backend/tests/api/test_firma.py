"""Las frases fijas de la firma: Sol, Luna y Ascendente en palabras.

Son contenido versionado. Que falte una sería una carta sin firma para quien
tenga justo ese signo, así que la tabla se prueba completa.
"""

import itertools

import pytest

from api.firma_frases import CUERPOS, SIGNOS, firma, frase

IDIOMAS = ("es", "en", "pt")


def test_son_tres_cuerpos_y_doce_signos():
    assert CUERPOS == ("Sun", "Moon", "Ascendant")
    assert len(SIGNOS) == 12


@pytest.mark.parametrize("lang", IDIOMAS)
def test_hay_frase_para_cada_combinacion(lang):
    for cuerpo, signo in itertools.product(CUERPOS, SIGNOS):
        assert frase(cuerpo, signo, lang).strip(), (cuerpo, signo, lang)


def test_no_hay_claves_de_sobra():
    from api.firma_frases import _FRASES

    esperadas = {f"{c}|{s}" for c, s in itertools.product(CUERPOS, SIGNOS)}
    assert set(_FRASES) == set(IDIOMAS)
    for lang in IDIOMAS:
        assert set(_FRASES[lang]) == esperadas, lang


@pytest.mark.parametrize("lang", IDIOMAS)
def test_las_frases_tienen_largo_de_una_oracion(lang):
    for cuerpo, signo in itertools.product(CUERPOS, SIGNOS):
        palabras = len(frase(cuerpo, signo, lang).split())
        assert 12 <= palabras <= 40, (cuerpo, signo, lang, palabras)


def _data(time_known: bool) -> dict:
    return {
        "time_known": time_known,
        "placements": [
            {"name": "Sun", "sign": "Gem"},
            {"name": "Moon", "sign": "Sco"},
            {"name": "Mercury", "sign": "Tau"},
        ],
        "angles": [{"name": "Ascendant", "sign": "Can"}] if time_known else None,
    }


def test_firma_con_hora_tiene_tres_lineas():
    lineas = firma(_data(time_known=True))
    assert [linea["cuerpo"] for linea in lineas] == ["Sun", "Moon", "Ascendant"]
    assert lineas[0]["signo"] == "Gem"
    assert set(lineas[0]["frases"]) == set(IDIOMAS)


def test_firma_sin_hora_no_tiene_ascendente():
    lineas = firma(_data(time_known=False))
    assert [linea["cuerpo"] for linea in lineas] == ["Sun", "Moon"]
