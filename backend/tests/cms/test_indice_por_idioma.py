"""El blog es en tres idiomas: tiene que haber un índice por idioma (RF4).

`NoteIndexPage` tenía `max_count = 1`, que Wagtail cuenta GLOBAL —
`Page.can_create_at` hace `cls.objects.count() < cls.max_count` sin filtrar por
locale (wagtail/models/pages.py). Creado el índice en español, el admin dejaba
de ofrecer el tipo en el menú de "añadir página hija" de las raíces inglesa y
portuguesa, y la vista de creación cortaba con PermissionDenied. Como las notas
sólo cuelgan de un índice (`NotePage.parent_page_types`), esos dos idiomas se
quedaban sin ninguna nota posible: el blog multiidioma no se podía armar.
"""
import pytest
from wagtail.models import Locale, Site

from cms.models import NoteIndexPage, NotePage


@pytest.fixture
def raices(db):
    """La raíz del árbol en español y su traducción a inglés."""
    raiz_es = Site.objects.get(is_default_site=True).root_page
    raiz_en = raiz_es.copy_for_translation(Locale.objects.get(language_code="en"))
    return raiz_es, raiz_en


@pytest.mark.django_db
def test_se_puede_crear_el_indice_en_ingles_habiendo_uno_en_espanol(raices):
    raiz_es, raiz_en = raices
    raiz_es.add_child(instance=NoteIndexPage(title="Notas", slug="notas"))

    assert NoteIndexPage.can_create_at(raiz_en) is True


@pytest.mark.django_db
def test_no_se_pueden_crear_dos_indices_en_el_mismo_idioma(raices):
    raiz_es, _ = raices
    raiz_es.add_child(instance=NoteIndexPage(title="Notas", slug="notas"))

    assert NoteIndexPage.can_create_at(raiz_es) is False


@pytest.mark.django_db
def test_una_nota_puede_colgar_del_indice_ingles(raices):
    """La consecuencia real del bug: sin índice inglés no hay notas inglesas.

    La inglesa se crea como traducción de una española: suelta, el modelo la
    rechaza (`NotePage.clean`, tests/cms/test_traducir.py).
    """
    raiz_es, _ = raices
    indice_es = NoteIndexPage(title="Notas", slug="notas")
    raiz_es.add_child(instance=indice_es)
    en = Locale.objects.get(language_code="en")
    indice_es.copy_for_translation(en)

    nota_es = NotePage(
        title="Sol, Luna y Ascendente",
        slug="sol-luna-ascendente",
        fecha="2026-07-14",
        bajada="Los tres que no son lo mismo.",
        cuerpo="<p>El Sol es lo que quiere ser.</p>",
        live=True,
    )
    indice_es.add_child(instance=nota_es)
    nota_en = nota_es.copy_for_translation(en)
    nota_en.title = "Sun, Moon and Ascendant"
    nota_en.cuerpo = "<p>The Sun is what it wants to be.</p>"
    nota_en.live = True
    nota_en.save()

    assert NotePage.objects.filter(locale__language_code="en").count() == 1
