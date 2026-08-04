"""Publicar una nota la hace visible sin correr un build a mano.

Sin esto el CMS no cumple su función: el editor publica, no ve su nota y lo
reporta como bug (RF10).
"""
from unittest.mock import patch

import pytest
from wagtail.models import Page

from cms.models import NoteIndexPage, NotePage


@pytest.fixture
def nota(db):
    raiz = Page.objects.get(depth=1)
    indice = NoteIndexPage(title="Notas", slug="notas")
    raiz.add_child(instance=indice)
    nota = NotePage(
        title="Sol, Luna y Ascendente", slug="sol-luna-ascendente",
        fecha="2026-07-14", bajada="x", cuerpo="<p>y</p>",
    )
    indice.add_child(instance=nota)
    return nota


@pytest.mark.django_db
def test_publicar_avisa_al_frontend(nota, settings):
    settings.REVALIDATE_URL = "https://astra.dothecode.com/api/revalidate"
    settings.REVALIDATE_SECRET = "un-secreto"
    with patch("cms.signals.requests.post") as post:
        nota.save_revision().publish()
    post.assert_called_once()
    enviado = post.call_args.kwargs["json"]
    assert enviado["slug"] == "sol-luna-ascendente"
    assert enviado["secret"] == "un-secreto"


@pytest.mark.django_db
def test_sin_configuracion_no_avisa_ni_rompe(nota, settings):
    settings.REVALIDATE_URL = ""
    with patch("cms.signals.requests.post") as post:
        nota.save_revision().publish()
    post.assert_not_called()


@pytest.mark.django_db
def test_si_el_frontend_falla_la_publicacion_igual_ocurre(nota, settings):
    settings.REVALIDATE_URL = "https://astra.dothecode.com/api/revalidate"
    settings.REVALIDATE_SECRET = "un-secreto"
    with patch("cms.signals.requests.post", side_effect=OSError("sin red")):
        nota.save_revision().publish()
    nota.refresh_from_db()
    assert nota.live is True
