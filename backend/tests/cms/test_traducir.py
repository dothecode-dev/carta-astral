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

import json
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


def _cuerpo(texto):
    """El cuerpo como lo manda el editor Draftail del admin."""
    return json.dumps(
        {
            "blocks": [
                {
                    "key": "a1b2c",
                    "text": texto,
                    "type": "unstyled",
                    "depth": 0,
                    "inlineStyleRanges": [],
                    "entityRanges": [],
                    "data": {},
                }
            ],
            "entityMap": {},
        }
    )


def _formulario(title, slug, cuerpo, publicar):
    datos = {
        "title": title,
        "slug": slug,
        "fecha": "2026-11-09",
        "bajada": "The house of the word.",
        "cuerpo": _cuerpo(cuerpo),
        "comments-TOTAL_FORMS": "0",
        "comments-INITIAL_FORMS": "0",
        "comments-MIN_NUM_FORMS": "0",
        "comments-MAX_NUM_FORMS": "1000",
    }
    if publicar:
        datos["action-publish"] = "action-publish"
    return datos


@pytest.fixture
def staff_client(db):
    staff = User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
    client = Client()
    client.force_login(staff)
    return client


@pytest.mark.django_db
def test_agregar_pagina_en_ingles_sin_original_se_rechaza(admin_montado, nota_es, staff_client):
    """El camino viejo: crear la inglesa a mano bajo su índice la dejaba suelta."""
    indice_en = NoteIndexPage.objects.get(locale__language_code="en")

    resp = staff_client.post(
        f"/{ADMIN}/pages/add/cms/notepage/{indice_en.id}/",
        _formulario("House III", "house-3-communication", "The word.", publicar=True),
    )

    assert resp.status_code == 200
    assert "no está vinculada a una nota en español" in resp.content.decode()
    assert not NotePage.objects.filter(locale__language_code="en").exists()


@pytest.mark.django_db
def test_publicar_la_traduccion_con_el_cuerpo_en_espanol_se_rechaza(
    admin_montado, nota_es, staff_client
):
    _traducir(staff_client, nota_es, "en")
    nota_en = NotePage.objects.get(locale__language_code="en")

    resp = staff_client.post(
        f"/{ADMIN}/pages/{nota_en.id}/edit/",
        _formulario("House III", "house-3-communication", "Cómo pensás y cómo hablás.", publicar=True),
    )

    assert resp.status_code == 200
    assert "falta traducirlo" in resp.content.decode()
    nota_en.refresh_from_db()
    assert nota_en.live is False


@pytest.mark.django_db
def test_el_borrador_de_la_traduccion_se_puede_guardar_sin_traducir(
    admin_montado, nota_es, staff_client
):
    """Guardar a medias tiene que andar: el control es al publicar."""
    _traducir(staff_client, nota_es, "en")
    nota_en = NotePage.objects.get(locale__language_code="en")

    resp = staff_client.post(
        f"/{ADMIN}/pages/{nota_en.id}/edit/",
        _formulario("House III", "house-3-communication", "Cómo pensás y cómo hablás.", publicar=False),
    )

    assert resp.status_code == 302, resp.content.decode()[:500]


@pytest.mark.django_db
def test_la_traduccion_traducida_se_publica_vinculada(admin_montado, nota_es, staff_client):
    _traducir(staff_client, nota_es, "en")
    nota_en = NotePage.objects.get(locale__language_code="en")

    resp = staff_client.post(
        f"/{ADMIN}/pages/{nota_en.id}/edit/",
        _formulario("House III", "house-3-communication", "How you think and speak.", publicar=True),
    )

    assert resp.status_code == 302, resp.content.decode()[:500]
    nota_en.refresh_from_db()
    assert nota_en.live is True
    assert nota_en.slug == "house-3-communication"
    assert nota_en.translation_key == nota_es.translation_key


@pytest.mark.django_db
def test_agregar_pagina_en_espanol_sigue_andando(admin_montado, nota_es, staff_client):
    """La española es la original: se crea con «Agregar página», como siempre."""
    indice_es = NoteIndexPage.objects.get(locale__language_code="es")

    resp = staff_client.post(
        f"/{ADMIN}/pages/add/cms/notepage/{indice_es.id}/",
        _formulario("La casa IV", "casa-4-raices", "Las raíces.", publicar=True),
    )

    assert resp.status_code == 302, resp.content.decode()[:500]
    assert NotePage.objects.get(slug="casa-4-raices").live is True
