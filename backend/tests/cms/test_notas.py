"""Una nota es un texto publicable, traducible y con portada.

Cada idioma es una página independiente: se publica por separado y tiene su
propio slug (RF4).
"""
from datetime import date

import pytest
from wagtail.models import Locale, Page

from cms.models import NoteIndexPage, NotePage


@pytest.fixture
def indice(db):
    raiz = Page.objects.get(depth=1)
    indice = NoteIndexPage(title="Notas", slug="notas")
    raiz.add_child(instance=indice)
    return indice


@pytest.mark.django_db
def test_una_nota_guarda_su_contenido(indice):
    nota = NotePage(
        title="Sol, Luna y Ascendente",
        slug="sol-luna-ascendente",
        bajada="Los tres que no son lo mismo.",
        cuerpo="<p>El Sol es lo que quiere ser.</p>",
    )
    indice.add_child(instance=nota)
    guardada = NotePage.objects.get(slug="sol-luna-ascendente")
    assert guardada.bajada == "Los tres que no son lo mismo."
    assert "El Sol" in guardada.cuerpo


@pytest.mark.django_db
def test_una_nota_sin_fecha_toma_la_de_hoy(indice):
    # `fecha` no es obligatoria al crear: nace con la fecha de hoy y se puede
    # adelantar o atrasar después desde el panel (por ejemplo, para programar
    # la publicación).
    nota = NotePage(
        title="Sin fecha explícita",
        slug="sin-fecha-explicita",
        bajada="x",
        cuerpo="<p>x</p>",
    )
    indice.add_child(instance=nota)
    guardada = NotePage.objects.get(slug="sin-fecha-explicita")
    assert guardada.fecha == date.today()


@pytest.mark.django_db
def test_los_tres_idiomas_existen():
    codigos = set(Locale.objects.values_list("language_code", flat=True))
    assert {"es", "en", "pt"} <= codigos


@pytest.mark.django_db
def test_una_nota_solo_admite_notas_debajo(indice):
    assert NotePage in indice.specific_class.allowed_subpage_models()
    assert NoteIndexPage not in NotePage.allowed_subpage_models()
