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
    assert "Persona A" in texto and "madre o padre" in texto and "hijo o hija" in texto
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
