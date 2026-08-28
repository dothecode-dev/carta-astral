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
