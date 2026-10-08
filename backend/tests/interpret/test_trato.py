import pytest

from interpret import generator
from interpret.prompts import SECCIONES
from interpret.trato import instruccion


def _espiar(monkeypatch):
    vistos = []
    monkeypatch.setattr(
        generator,
        "_stream_text",
        lambda client, model, system, content, max_tokens: vistos.append((system, content)) or "ok",
    )
    return vistos


@pytest.mark.parametrize("trato", ["femenino", "masculino", "neutro", ""])
def test_ingles_no_lleva_instruccion(trato):
    assert instruccion(trato, "en") == ""


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_femenino_y_masculino_piden_consistencia(lang):
    fem, masc = instruccion("femenino", lang), instruccion("masculino", lang)
    assert fem and masc and fem != masc


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_sin_elegir_es_neutro(lang):
    assert instruccion("", lang) == instruccion("neutro", lang) != ""


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_valor_desconocido_es_neutro(lang):
    assert instruccion("otro", lang) == instruccion("neutro", lang)


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_el_system_de_la_seccion_no_cambia_con_el_trato(monkeypatch, lang):
    vistos = _espiar(monkeypatch)
    generator.build_seccion({"time_known": True}, SECCIONES[0], lang, "", None, trato="femenino")
    generator.build_seccion({"time_known": True}, SECCIONES[0], lang, "", None)
    assert vistos[0][0] == vistos[1][0]


def test_la_breve_lleva_el_trato_en_el_contenido_y_el_system_no_cambia(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.build_interpretation({"time_known": True}, "es", "v2", None, trato="femenino")
    generator.build_interpretation({"time_known": True}, "es", "v2", None)
    (sys_con, cont_con), (sys_sin, cont_sin) = vistos
    assert sys_con == sys_sin
    assert instruccion("femenino", "es") in cont_con
    assert instruccion("neutro", "es") in cont_sin


def test_la_seccion_lleva_el_trato(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.build_seccion({"time_known": True}, SECCIONES[0], "pt", "", None, trato="masculino")
    assert instruccion("masculino", "pt") in vistos[0][1]


def test_la_instruccion_de_la_seccion_va_al_final_despues_de_reparto_y_previo(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.build_seccion(
        {"time_known": False}, SECCIONES[0], "es", "LO PREVIO", None, reparto="EL REPARTO", trato="femenino"
    )
    content = vistos[0][1]
    nota = instruccion("femenino", "es")
    assert content.endswith(nota)
    assert content.index("EL REPARTO") < content.index("LO PREVIO") < content.index(nota)
    assert content.index(generator._DEGRADED_NOTES["es"]) < content.index("EL REPARTO")


def test_la_traduccion_lleva_el_trato_del_destino_en_el_system(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.translate_interpretation("texto", "pt", None, trato="femenino")
    system, content = vistos[0]
    assert content == "texto"
    assert instruccion("femenino", "pt") in system[-1]["text"]
    assert "cache_control" not in system[-1]


def test_traduccion_a_ingles_no_cambia_el_system(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.translate_interpretation("texto", "en", None, trato="femenino")
    generator.translate_interpretation("texto", "en", None)
    assert vistos[0] == vistos[1]
    assert len(vistos[0][0]) == 1


def test_en_ingles_todo_queda_igual(monkeypatch):
    vistos = _espiar(monkeypatch)
    generator.build_interpretation({"time_known": True}, "en", "v2", None, trato="femenino")
    generator.build_interpretation({"time_known": True}, "en", "v2", None)
    generator.build_seccion({"time_known": True}, SECCIONES[0], "en", "", None, trato="femenino")
    generator.build_seccion({"time_known": True}, SECCIONES[0], "en", "", None)
    assert vistos[0] == vistos[1]
    assert vistos[2] == vistos[3]


@pytest.mark.parametrize(
    "lang, prohibidas",
    [("es", ("vos mismo", "vos misma")), ("pt", ("você mesmo", "você mesma"))],
)
def test_la_neutra_nombra_el_intensificador_para_prohibirlo(lang, prohibidas):
    texto = instruccion("neutro", lang)
    for forma in prohibidas:
        assert f"«{forma}»" in texto


def test_la_neutra_pt_nombra_los_pronombres_obliquos_para_prohibirlos():
    texto = instruccion("neutro", "pt")
    assert "«o empurra»" in texto
    assert "«consigo mesmo»" in texto
