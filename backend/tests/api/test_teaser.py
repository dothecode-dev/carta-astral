"""`api.teaser`: los párrafos fijos y el índice bloqueado del informe.

Se prueba sobre cartas calculadas de verdad (`calcular`), no sobre dicts a
mano: lo que importa es que el índice coincida con el reparto del informe.
"""

import logging
from collections import Counter
from pathlib import Path

import pytest

from api import teaser as mod
from api.chart_service import calcular
from api.serializers import serialize_chart_data
from interpret import reparto
from interpret.prompts import SECCIONES

CECI = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
}
# Seis cartas fijas, con y sin hora, en hemisferios y décadas distintos.
CARTAS = [
    CECI,
    {**CECI, "date": "1985-11-02", "time": "06:10"},
    {**CECI, "date": "1990-02-14", "time": "23:45", "lat": 40.4, "lng": -3.7},
    {**CECI, "date": "2001-08-19", "time": None, "time_known": False},
    {**CECI, "date": "1968-12-25", "time": None, "time_known": False, "lat": 51.5, "lng": -0.12},
    {**CECI, "date": "1999-03-08", "time": "12:00", "lat": 35.7, "lng": 139.7},
]
# Los textos de prueba: no dependen del contenido real del JSON.
SIGNOS = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis")


def _data(payload: dict) -> dict:
    return serialize_chart_data(calcular(payload).data)


@pytest.fixture(autouse=True)
def textos(monkeypatch):
    falsos = {
        lang: {f"{c}|{s}": f"{lang} {c} {s}" for c in mod.CUERPOS_TEASER for s in SIGNOS}
        for lang in ("es", "en", "pt")
    }
    monkeypatch.setattr(mod, "_TEXTOS", falsos)


def test_bloques_en_orden_de_cuerpos():
    t = mod.teaser(_data(CECI))
    assert [b["cuerpo"] for b in t["bloques"]] == list(mod.CUERPOS_TEASER)
    sol = t["bloques"][0]
    assert sol["textos"] == {lang: f"{lang} Sun {sol['signo']}" for lang in ("es", "en", "pt")}


def test_sin_hora_no_hay_ascendente_ni_secciones_con_hora():
    t = mod.teaser(_data(CARTAS[3]))
    assert "Ascendant" not in [b["cuerpo"] for b in t["bloques"]]
    con_hora = {s.slug for s in SECCIONES if s.requiere_hora}
    assert con_hora
    assert not con_hora & {s["slug"] for s in t["indice"]}


def test_luna_dudosa_no_tiene_bloque_ni_tema():
    data = _data(CARTAS[3])
    data["flags"]["moon_sign_uncertain"] = True
    t = mod.teaser(data)
    assert "Moon" not in [b["cuerpo"] for b in t["bloques"]]
    luna = reparto.NOMBRES["es"]["Moon"]
    temas = [x["es"] for s in t["indice"] for x in s["temas"]]
    assert not any(x.startswith(luna) for x in temas)


@pytest.mark.parametrize("payload", CARTAS)
def test_todo_tema_mostrado_es_propio_de_su_seccion(payload):
    """La propiedad que sostiene el gancho: lo que el teaser promete, el informe lo trata.
    Se compara por `Tema.clave`, no por el texto que arma el propio teaser."""
    data = _data(payload)
    todos = reparto.temas(data)
    aplicables = [s for s in SECCIONES if data["time_known"] or not s.requiere_hora]
    mostrados = 0
    for s in aplicables:
        propios = {t.clave for t in todos if t.duena == s.slug}
        elegidos = mod._elegidos(data, s.slug)
        assert {t.clave for t in elegidos} <= propios
        mostrados += len(elegidos)
    # Que no pase vacío: todas las cartas fijas tienen planetas propios en alguna sección.
    assert mostrados >= 4
    # Y lo que sale en el índice es exactamente lo elegido, nombrado.
    for s in mod.teaser(data)["indice"]:
        esperado = [{lang: mod._nombre_tema(t, lang, data) for lang in ("es", "en", "pt")}
                    for t in mod._elegidos(data, s["slug"])]
        assert s["temas"] == esperado


@pytest.mark.parametrize("payload", CARTAS)
def test_como_maximo_dos_temas_y_tensos_primero(payload):
    data = _data(payload)
    todos = reparto.temas(data)
    for s in mod.teaser(data)["indice"]:
        assert len(s["temas"]) <= 2
        tensos = {
            mod._nombre_tema(t, "es", data) for t in todos
            if t.duena == s["slug"] and t.tipo == "aspecto" and t.aspecto in reparto.TENSOS
        }
        mostrados = [x["es"] for x in s["temas"]]
        # Si la sección tiene tensos, el primero mostrado es uno de ellos.
        if tensos and mostrados:
            assert mostrados[0] in tensos


def test_prioridad_aspecto_antes_que_planeta():
    # Un aspecto tenso es siempre de «tensiones»; en «afectos» el aspecto es un trígono.
    data = {
        "time_known": False, "flags": {},
        "placements": [{"name": "Venus", "sign": "Sco"}, {"name": "Mars", "sign": "Pis"}],
        "aspects": [{"p1": "Venus", "p2": "Mars", "aspect": "trine", "orbit": 1.0}],
        "angles": None,
    }
    afectos = next(s for s in mod.teaser(data)["indice"] if s["slug"] == "afectos")
    assert [x["es"] for x in afectos["temas"]][0] == "Venus en trígono con Marte"
    assert afectos["temas"][1]["es"] == "Venus en Escorpio"
    assert afectos["temas"][1]["en"] == "Venus in Scorpio"
    assert afectos["temas"][1]["pt"] == "Vênus em Escorpião"


def test_nunca_muestra_sol_mercurio_ni_sol_venus_en_conjuncion():
    data = {
        "time_known": False, "flags": {},
        "placements": [{"name": n, "sign": "Gem"} for n in ("Sun", "Mercury", "Venus")],
        "aspects": [
            {"p1": "Sun", "p2": "Mercury", "aspect": "conjunction", "orbit": 1.0},
            {"p1": "Sun", "p2": "Venus", "aspect": "conjunction", "orbit": 1.0},
        ],
        "angles": None,
    }
    temas = [x["es"] for s in mod.teaser(data)["indice"] for x in s["temas"]]
    assert not any("conjunción" in x for x in temas)


def test_tensos_primero_dentro_de_tensiones():
    data = {
        "time_known": False, "flags": {},
        "placements": [{"name": "Venus", "sign": "Sco"}, {"name": "Saturn", "sign": "Leo"}],
        "aspects": [
            {"p1": "Sun", "p2": "Moon", "aspect": "trine", "orbit": 1.0},
            {"p1": "Venus", "p2": "Saturn", "aspect": "square", "orbit": 1.0},
        ],
        "angles": None,
    }
    tensiones = next(s for s in mod.teaser(data)["indice"] if s["slug"] == "tensiones")
    assert [x["es"] for x in tensiones["temas"]] == ["Venus en cuadratura con Saturno"]


def test_sintesis_va_sin_temas():
    s = next(s for s in mod.teaser(_data(CECI))["indice"] if s["slug"] == "sintesis")
    assert s["temas"] == []


def test_seccion_sin_temas_va_solo_con_titulo():
    data = {"time_known": False, "flags": {}, "placements": [{"name": "Sun", "sign": "Leo"}],
            "aspects": [], "angles": None}
    indice = {s["slug"]: s for s in mod.teaser(data)["indice"]}
    assert indice["afectos"]["temas"] == []
    assert indice["afectos"]["titulos"]["es"]


def test_mismo_data_mismo_teaser():
    assert mod.teaser(_data(CECI)) == mod.teaser(_data(CECI))


@pytest.mark.parametrize("payload", [CECI, CARTAS[3]])
def test_informe_cuenta_secciones_y_redondea_palabras_a_miles(payload):
    data = _data(payload)
    aplicables = [s for s in SECCIONES if data["time_known"] or not s.requiere_hora]
    informe = mod.teaser(data)["informe"]
    assert informe["secciones"] == len(aplicables)
    assert informe["palabras"] % 1000 == 0
    assert abs(informe["palabras"] - sum(s.palabras for s in aplicables)) <= 500


def test_cuerpo_faltante_se_omite_y_loguea(monkeypatch, caplog):
    textos = {lang: dict(d) for lang, d in mod._TEXTOS.items()}
    sol = mod.teaser(_data(CECI))["bloques"][0]["signo"]
    del textos["en"][f"Sun|{sol}"]
    monkeypatch.setattr(mod, "_TEXTOS", textos)
    with caplog.at_level(logging.WARNING, logger="api.teaser"):
        t = mod.teaser(_data(CECI))
    assert "Sun" not in [b["cuerpo"] for b in t["bloques"]]
    assert "Moon" in [b["cuerpo"] for b in t["bloques"]]
    assert "falta texto cuerpo=Sun" in caplog.text


def test_no_importa_el_llm():
    fuente = Path(mod.__file__).read_text(encoding="utf-8")
    assert "anthropic" not in fuente
    assert "interpret.generator" not in fuente


def test_sin_textos_reales_devuelve_bloques_vacios_sin_romper(monkeypatch):
    monkeypatch.setattr(mod, "_TEXTOS", {"es": {}, "en": {}, "pt": {}})
    t = mod.teaser(_data(CECI))
    assert t["bloques"] == []
    assert Counter(s["slug"] for s in t["indice"])


def test_nomenclatura_exacta_por_idioma():
    data = {
        "time_known": True, "flags": {},
        "placements": [{"name": "Venus", "sign": "Sco", "house": "Eighth_House"},
                       {"name": "Sun", "sign": "Leo", "house": "First_House"}],
        "angles": [{"name": "Ascendant", "sign": "Leo"}],
    }
    def nombre(t):
        return {lang: mod._nombre_tema(t, lang, data) for lang in ("es", "en", "pt")}

    venus = nombre(reparto.Tema("planeta", "afectos", ("Venus",)))
    assert venus == {"es": "Venus en Escorpio en la casa VIII",
                     "en": "Venus in Scorpio in the 8th house",
                     "pt": "Vênus em Escorpião na casa VIII"}
    cumulo = nombre(reparto.Tema("cumulo", "casas", ("Sun", "Venus", "Mars"), casa="Third_House"))
    assert cumulo == {"es": "tres planetas en la casa III",
                      "en": "three planets in the 3rd house",
                      "pt": "três planetas na casa III"}
    def asp(a, b, tipo):
        return nombre(reparto.Tema("aspecto", "x", (a, b), aspecto=tipo))

    assert asp("Sun", "Moon", "opposition") == {
        "es": "Sol en oposición a la Luna", "en": "Sun opposite Moon", "pt": "Sol em oposição à Lua"}
    assert asp("Mars", "Ascendant", "conjunction") == {
        "es": "Marte en conjunción con el Ascendente", "en": "Mars conjunct Ascendant",
        "pt": "Marte em conjunção com o Ascendente"}
    assert asp("Venus", "Saturn", "square")["es"] == "Venus en cuadratura con Saturno"
    assert asp("Venus", "Sun", "opposition") == {
        "es": "Venus en oposición al Sol", "en": "Venus opposite Sun", "pt": "Vênus em oposição ao Sol"}
    assert asp("Venus", "Moon", "trine")["pt"] == "Vênus em trígono com a Lua"
