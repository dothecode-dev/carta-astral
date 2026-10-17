import pytest

from interpret.vinculo import contenido_vinculo, secciones_vinculo

DATOS = {
    "tipo": "familia",
    "persona_a": {"rol": "progenitor", "carta": {"time_known": True}},
    "persona_b": {"rol": "hijo", "carta": {"time_known": False}},
    "aspectos_cruzados": [], "planetas_de_a_en_casas_de_b": None,
    "planetas_de_b_en_casas_de_a": {"Sun": 4},
}


def test_ocho_secciones_con_hora_y_siete_sin():
    assert len(secciones_vinculo("pareja", hay_hora=True)) == 8
    sin = secciones_vinculo("pareja", hay_hora=False)
    assert len(sin) == 7 and "casas" not in {s.slug for s in sin}


def test_en_trabajo_la_cuarta_es_confianza_y_reconocimiento():
    cuarta = secciones_vinculo("trabajo", hay_hora=True)[3]
    assert "confianza" in cuarta.titulo["es"].lower()
    assert "afecto" in secciones_vinculo("pareja", hay_hora=True)[3].titulo["es"].lower()


def test_el_contenido_nombra_los_roles_y_el_tipo():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    texto = contenido_vinculo(DATOS, sec, "es", "")
    assert "Persona A es quien tiene el rol de crianza" in texto
    assert "Persona B es quien recibió la crianza de la otra persona" in texto
    assert "familia" in texto.lower()


def test_cambiar_los_roles_cambia_el_contenido():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    otro = {**DATOS, "persona_a": {**DATOS["persona_a"], "rol": "hijo"},
            "persona_b": {**DATOS["persona_b"], "rol": "progenitor"}}
    assert contenido_vinculo(DATOS, sec, "es", "") != contenido_vinculo(otro, sec, "es", "")


def test_avisa_quien_no_tiene_hora():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    texto = contenido_vinculo(DATOS, sec, "es", "")
    assert "Sin hora de nacimiento para Persona B" in texto
    assert "Sin hora de nacimiento para Persona A" not in texto


def test_el_rol_no_reemplaza_a_la_persona():
    """El alias sólo se puede mostrar donde el modelo escribió «Persona A»: si
    la nombra por su rol («la jefa»), el alias no aparece nunca (RF22)."""
    from interpret.vinculo import _SYSTEM

    assert "por su rol" not in _SYSTEM["es"]
    assert "by their role" not in _SYSTEM["en"]
    assert "pelo papel" not in _SYSTEM["pt"]


def _con_generos(ga, gb):
    return {**DATOS, "persona_a": {**DATOS["persona_a"], "genero": ga},
            "persona_b": {**DATOS["persona_b"], "genero": gb}}


def test_el_rol_se_escribe_con_el_genero_de_cada_persona():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    texto = contenido_vinculo(_con_generos("femenino", "masculino"), sec, "es", "")
    assert "Persona A es la madre" in texto and "Persona B es el hijo" in texto
    assert "madre o padre" not in texto


def test_sin_genero_el_rol_queda_neutro_y_se_pide_redaccion_neutra():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    texto = contenido_vinculo(_con_generos("", ""), sec, "es", "")
    assert "Persona A es quien tiene el rol de crianza" in texto and "neutra" in texto


def test_el_genero_se_pide_tambien_sin_rol():
    sec = secciones_vinculo("pareja", hay_hora=True)[0]
    datos = {**_con_generos("femenino", "masculino"),
             "tipo": "pareja",
             "persona_a": {"rol": "", "carta": {"time_known": True}, "genero": "femenino"},
             "persona_b": {"rol": "", "carta": {"time_known": True}, "genero": "masculino"}}
    texto = contenido_vinculo(datos, sec, "es", "")
    assert "Persona A es mujer" in texto and "Persona B es varón" in texto


def test_neutro_se_redacta_igual_que_sin_genero():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    assert (contenido_vinculo(_con_generos("neutro", "neutro"), sec, "es", "")
            == contenido_vinculo(_con_generos("", ""), sec, "es", ""))


def test_el_prompt_lleva_la_guia_larga_de_cada_persona():
    from interpret.trato import instruccion_persona

    sec = secciones_vinculo("familia", hay_hora=True)[0]
    texto = contenido_vinculo(_con_generos("neutro", "femenino"), sec, "es", "")
    assert instruccion_persona("neutro", "es", "Persona A") in texto
    assert instruccion_persona("femenino", "es", "Persona B") in texto


def test_la_seccion_del_vinculo_no_razona(monkeypatch):
    """Medido en staging el 10-10: con la guía neutra larga, Sonnet razonaba
    hasta agotar el techo de la sección (8.400 de 8.400 tokens) y el informe
    fallaba. El techo mide texto; el género lo cubre el juez."""
    from interpret import vinculo

    vistos = []
    monkeypatch.setattr(
        vinculo, "_stream_text",
        lambda client, model, system, content, max_tokens, thinking=None: vistos.append(thinking) or "ok",
    )
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    vinculo.build_seccion_vinculo(_con_generos("neutro", ""), sec, "es", "", object())
    assert vistos == [{"type": "disabled"}]


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_sin_genero_el_rol_no_trae_las_formas_que_la_guia_prohibe(lang):
    """La guía neutra prohíbe «madre o padre»; el rol neutro no puede traerlo."""
    from interpret.vinculo import ETIQUETAS_ROL

    for rol, por_idioma in ETIQUETAS_ROL.items():
        etiqueta = por_idioma[lang][""]
        doble = " o " if lang == "es" else " ou "  # en pt « o » es artículo
        assert doble not in etiqueta, (rol, etiqueta)
        assert "progenitor" not in etiqueta


def test_avisa_la_luna_dudosa_de_quien_no_tiene_hora():
    sec = secciones_vinculo("familia", hay_hora=True)[0]
    datos = {**DATOS, "persona_b": {**DATOS["persona_b"], "carta": {
        "time_known": False,
        "flags": {"moon_sign_uncertain": True, "moon_sign_options": ["Leo", "Vir"]},
    }}}
    texto = contenido_vinculo(datos, sec, "es", "")
    cola = texto.rsplit("}", 1)[-1]
    assert "Luna de Persona B" in cola and "Leo" in cola and "Vir" in cola
    assert "Luna de Persona B" not in contenido_vinculo(DATOS, sec, "es", "")
