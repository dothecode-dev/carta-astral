from interpret.prompts import PROMPT_VERSION, SECCIONES


def test_son_ocho_secciones_en_orden():
    assert len(SECCIONES) == 8
    assert [s.slug for s in SECCIONES] == [
        "firma", "mente", "afectos", "trabajo",
        "tensiones", "lentos", "casas", "sintesis",
    ]


def test_cada_seccion_tiene_titulo_y_foco_en_los_tres_idiomas():
    for s in SECCIONES:
        for lang in ("es", "en", "pt"):
            assert s.titulo[lang].strip(), f"{s.slug} sin título en {lang}"
            assert s.foco[lang].strip(), f"{s.slug} sin foco en {lang}"


def test_el_total_apunta_a_unas_6400_palabras():
    assert 6000 <= sum(s.palabras for s in SECCIONES) <= 7000


def test_la_version_del_prompt_subio():
    # Cambiar los prompts sin subir la versión sirve prosa vieja del cache.
    assert PROMPT_VERSION == "v2"


def test_la_seccion_de_casas_esta_marcada_como_dependiente_de_la_hora():
    # Sin hora de nacimiento no hay casas ni ascendente: esa sección se omite.
    por_slug = {s.slug: s for s in SECCIONES}
    assert por_slug["casas"].requiere_hora is True
    assert por_slug["afectos"].requiere_hora is False


def test_cada_planeta_es_tema_del_foco_de_una_sola_seccion():
    # Spec 2026-10-07 RF6b: dos focos que nombran el mismo planeta son dos
    # secciones que lo explican. La síntesis no cuenta: lo usa todo.
    import re

    from interpret.prompts import SECCIONES

    planetas = {
        "es": ["Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno", "Urano", "Neptuno", "Plutón"],
        "en": ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"],
        "pt": ["Sol", "Lua", "Mercúrio", "Vênus", "Marte", "Júpiter", "Saturno", "Urano", "Netuno", "Plutão"],
    }
    for lang, nombres in planetas.items():
        for nombre in nombres:
            con = [
                s.slug for s in SECCIONES
                if s.slug != "sintesis" and re.search(rf"\b{nombre}\b", s.foco[lang])
            ]
            assert len(con) <= 1, (lang, nombre, con)
