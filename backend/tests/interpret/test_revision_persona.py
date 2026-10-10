"""El juez + reparación del género en tercera persona: el vínculo habla de
«Persona A» y «Persona B», cada una con su género (decisión del 10-10-2026).

Medido en staging el 10-10: un vínculo con las dos personas en neutro salió
con «se percibe a sí mismo», «sentirse seguro», «con solo mirarlo» y «como
progenitor» pese a la instrucción. Es el mismo patrón que el trato del
natal, y se cierra con la misma maquinaria apuntada a otra persona.
"""

import pytest

from interpret.revision_trato import revisar_persona, revisar_personas
from interpret.trato import instruccion_persona
from tests.interpret.llm_falso import ClienteFalso, _juez, _reemplazos, _system

TEXTO = (
    "## El encuentro\n\n"
    "Persona A llega con calma. El encanto de Persona B influye en cómo Persona A "
    "se percibe a sí mismo en su rol. Persona A puede saber que algo le pasa a "
    "Persona B con solo mirarlo, y viceversa. La Luna es protectora."
)


# --- la guía por persona ---


@pytest.mark.parametrize("lang", ["es", "pt", "en"])
def test_la_guia_nombra_a_la_persona(lang):
    for genero in ("femenino", "masculino", "neutro"):
        guia = instruccion_persona(genero, lang, "Persona A" if lang != "pt" else "Pessoa A")
        assert ("Persona A" in guia or "Pessoa A" in guia) and "{" not in guia


@pytest.mark.parametrize("lang", ["es", "pt", "en"])
def test_sin_elegir_o_desconocido_es_neutro(lang):
    neutro = instruccion_persona("neutro", lang, "Persona A")
    assert instruccion_persona("", lang, "Persona A") == neutro
    assert instruccion_persona("otro", lang, "Persona A") == neutro


def test_la_guia_neutra_trae_las_formas_que_se_escaparon():
    guia = instruccion_persona("neutro", "es", "Persona A")
    for forma in ("a sí mismo", "seguro", "mirarlo", "progenitor"):
        assert forma in guia


# --- la revisión de una persona ---


def test_neutro_repara_el_fragmento_de_la_persona():
    frag, ok = "con solo mirarlo", "con solo mirar a Persona B"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, ok)), _juez())
    assert revisar_persona(TEXTO, "neutro", "B", "es", cliente) == TEXTO.replace(frag, ok)
    juez = _system(cliente.llamadas[0])
    assert "Persona B" in juez and "quien lee" not in juez.lower()
    assert instruccion_persona("neutro", "es", "Persona B") in _system(cliente.llamadas[1])


def test_una_correccion_que_borra_a_la_persona_se_rechaza():
    frag = "Persona A se percibe a sí mismo"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, "se percibe a sí")))
    assert revisar_persona(TEXTO, "neutro", "A", "es", cliente) == TEXTO


def test_neutro_rechaza_una_correccion_con_pronombre_con_genero():
    frag = "con solo mirarlo"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, "con solo mirar a él")))
    assert revisar_persona(TEXTO, "neutro", "B", "es", cliente) == TEXTO


def test_femenino_rechaza_volver_al_masculino():
    frag = "se percibe a sí mismo"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, "se percibe a él mismo")))
    assert revisar_persona(TEXTO, "femenino", "A", "es", cliente) == TEXTO


def test_en_portugues_la_persona_es_pessoa():
    cliente = ClienteFalso(_juez())
    revisar_persona("Pessoa A chega calmo.", "neutro", "A", "pt", cliente)
    assert "Pessoa A" in _system(cliente.llamadas[0])


def test_en_ingles_tambien_se_revisa():
    """En tercera persona el inglés sí marca género (he/she)."""
    texto = "Person B feels it when he is seen."
    cliente = ClienteFalso(_juez("when he is seen"), _reemplazos(("when he is seen", "when they are seen")), _juez())
    assert revisar_persona(texto, "neutro", "B", "en", cliente) == "Person B feels it when they are seen."


def test_revisar_personas_revisa_a_las_dos_en_orden():
    cliente = ClienteFalso(_juez(), _juez())
    assert revisar_personas(TEXTO, ("neutro", "femenino"), "es", cliente) == TEXTO
    a, b = (_system(c) for c in cliente.llamadas)
    assert "Persona A" in a and "en neutro" in a
    assert "Persona B" in b and "en femenino" in b
