"""Los textos reales del teaser (`api/data/teaser_textos.json`), revisados a mano.

Acá no se monkeypatchea `_TEXTOS`: se prueba el contenido que se publica.
"""

import pytest

from api import teaser as mod
from api.chart_service import calcular
from api.firma_frases import SIGNOS
from api.management.commands.generar_textos_teaser import problemas_de_texto
from api.serializers import serialize_chart_data

IDIOMAS = ("es", "en", "pt")
CLAVES = {f"{c}|{s}" for c in mod.CUERPOS_TEASER for s in SIGNOS}

CECI = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
}


@pytest.mark.parametrize("lang", IDIOMAS)
def test_hay_texto_para_cada_combinacion(lang):
    assert set(mod._TEXTOS[lang]) == CLAVES


@pytest.mark.parametrize("lang", IDIOMAS)
def test_largo_entre_50_y_110_palabras(lang):
    fuera = {k: len(t.split()) for k, t in mod._TEXTOS[lang].items() if not 50 <= len(t.split()) <= 110}
    assert not fuera, f"{lang}: fuera de 50-110 palabras: {fuera}"


@pytest.mark.parametrize("lang", IDIOMAS)
def test_ningun_texto_tiene_problemas(lang):
    malos = {k: p for k, t in mod._TEXTOS[lang].items() if (p := problemas_de_texto(t, lang))}
    assert not malos, f"{lang}: " + "; ".join(f"{k} -> {p}" for k, p in malos.items())


def test_el_teaser_real_tiene_los_seis_bloques():
    t = mod.teaser(serialize_chart_data(calcular(CECI).data))
    assert [b["cuerpo"] for b in t["bloques"]] == list(mod.CUERPOS_TEASER)
    for b in t["bloques"]:
        for lang in IDIOMAS:
            assert b["textos"][lang].strip(), f"{b['cuerpo']} {b['signo']} sin texto en {lang}"
