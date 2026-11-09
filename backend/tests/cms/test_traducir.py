"""Las versiones en/pt de una nota tienen que nacer vinculadas a la española.

La web declara el `hreflang` de cada nota pidiendo `?translation_of=<id>` a la
API (`web/lib/notes.ts`), y Wagtail resuelve eso por `translation_key`. Cargando
cada idioma con «Agregar página» en su índice, cada página nacía con una key
nueva al azar: entre septiembre y noviembre de 2026 ocho tandas de notas
quedaron sueltas y compitiendo entre sí en el buscador, sin que nada avisara.

El botón «Traducir» de `wagtail.contrib.simple_translation` crea la copia en el
otro idioma con la misma key. Estos tests fijan que el botón exista y que lo
que crea quede vinculado, como borrador, bajo el índice del otro idioma.
"""

from importlib import reload

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import clear_url_caches
from wagtail.models import Locale, Site

import config.urls
from cms.models import NoteIndexPage, NotePage

User = get_user_model()

ADMIN = "panel-notas"


@pytest.fixture
def admin_montado(monkeypatch):
    """Monta el admin bajo un slug fijo, como hacen los demás tests del CMS."""
    try:
        with monkeypatch.context() as m:
            m.setenv("WAGTAIL_ADMIN_URL", ADMIN)
            reload(config.urls)
            clear_url_caches()
            yield
    finally:
        reload(config.urls)
        clear_url_caches()


@pytest.fixture
def nota_es(db):
    """Una nota española publicada, con el índice inglés ya vinculado al español."""
    en = Locale.objects.get(language_code="en")
    raiz_es = Site.objects.get(is_default_site=True).root_page
    raiz_es.copy_for_translation(en)
    indice_es = NoteIndexPage(title="Notas", slug="notas")
    raiz_es.add_child(instance=indice_es)
    indice_es.copy_for_translation(en)
    nota = NotePage(
        title="La casa III",
        slug="casa-3-comunicacion",
        fecha="2026-11-09",
        bajada="La casa de la palabra.",
        cuerpo="<p>Cómo pensás y cómo hablás.</p>",
        live=True,
    )
    indice_es.add_child(instance=nota)
    return nota


def _traducir(client, nota, codigo):
    locale = Locale.objects.get(language_code=codigo)
    return client.post(
        f"/{ADMIN}/translation/submit/page/{nota.id}/", {"locales": [locale.id]}
    )


@pytest.mark.django_db
def test_traducir_crea_la_nota_inglesa_vinculada_y_en_borrador(admin_montado, nota_es):
    staff = User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
    client = Client()
    # force_login: ver el comentario sobre axes en tests/api/test_admin.py.
    client.force_login(staff)

    resp = _traducir(client, nota_es, "en")

    assert resp.status_code == 302, resp.content[:300]
    nota_en = NotePage.objects.get(locale__language_code="en")
    assert nota_en.translation_key == nota_es.translation_key
    assert nota_en.get_parent().specific.locale.language_code == "en"
    # Nace en borrador: hasta que se reemplace el texto, no se publica nada en español
    # bajo /en/.
    assert nota_en.live is False


@pytest.mark.django_db
def test_traducir_no_responde_a_un_anonimo(admin_montado, nota_es):
    resp = _traducir(Client(), nota_es, "en")

    assert resp.status_code in (301, 302)
    assert "login" in resp.headers["Location"]
    assert not NotePage.objects.filter(locale__language_code="en").exists()
