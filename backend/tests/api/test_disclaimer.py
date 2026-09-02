"""Qué dice, y qué deja de decir, el pie de cada lectura.

Decisión de producto del 02-09-2026: el disclaimer deja de anunciar que el
texto lo escribió una IA. No es ocultarlo —la política de privacidad declara a
Anthropic como el proveedor que redacta las lecturas, y `check:legal` obliga a
que esa mención siga ahí; además la sección "Cómo se escribe tu lectura" de
`/cuenta` lo dice con todas las letras, y el bloque de compra enlaza a ella—
sino sacarlo del renglón que compite con la lectura misma.

Lo que no se puede perder es la advertencia: entretenimiento, no es consejo, y
sin valor predictivo. Eso protege al usuario y al producto, y es lo que este
test fija.
"""

import pytest

from api.interpretation_service import DISCLAIMERS

# Cómo se nombra a la IA en cada idioma. Si mañana alguien la vuelve a poner
# acá, que sea una decisión y no un descuido.
_NOMBRES_DE_LA_IA = (
    "inteligencia artificial",
    "artificial intelligence",
    "inteligência artificial",
    " ia ",
    " ai ",
)

# Las tres advertencias que el pie tiene que seguir dando, por idioma.
_ADVERTENCIAS = {
    "es": ("entretenimiento", "no es consejo", "predictivo"),
    "en": ("entertainment", "not medical", "predictive"),
    "pt": ("entretenimento", "não é conselho", "preditivo"),
}


@pytest.mark.parametrize("lang", sorted(DISCLAIMERS))
def test_el_disclaimer_no_nombra_a_la_ia(lang):
    texto = f" {DISCLAIMERS[lang].lower()} "

    for nombre in _NOMBRES_DE_LA_IA:
        assert nombre not in texto, (
            f"el disclaimer de {lang} volvió a nombrar a la IA: la mención vive "
            "en la política de privacidad y en la sección 'Cómo se escribe tu "
            "lectura' de /cuenta, no al pie de cada lectura"
        )


@pytest.mark.parametrize("lang", sorted(DISCLAIMERS))
def test_el_disclaimer_conserva_las_tres_advertencias(lang):
    """Sacar la mención a la IA no puede llevarse puesto el resto: sin esto,
    "acortar el disclaimer" termina borrando la advertencia entera."""
    texto = DISCLAIMERS[lang].lower()

    for advertencia in _ADVERTENCIAS[lang]:
        assert advertencia in texto, f"el disclaimer de {lang} perdió «{advertencia}»"


def test_los_tres_idiomas_dicen_lo_mismo():
    """Un idioma que advierta menos que otro es el que va a usar quien reclame."""
    assert set(DISCLAIMERS) == set(_ADVERTENCIAS)
