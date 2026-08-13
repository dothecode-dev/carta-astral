"""La API interna del admin de Wagtail, que es la que dibuja el árbol de páginas.

El proyecto fija permisos globales de DRF pensados para la app —token de cuenta
y `HasAccount`— y esa API los heredaba: el explorador lateral del admin recibía
403 y mostraba "Server Error" en vez del árbol. Estaba así desde el commit que
montó DRF, en junio de 2026, y se notó recién al usar el admin de verdad.

Quién puede entrar no lo decide DRF: todas las URLs del admin están envueltas
en `require_admin_access` (`wagtail/admin/urls/__init__.py`), que exige sesión y
el permiso `wagtailadmin.access_admin`. Estos tests fijan las dos mitades: que
quien pasó ese control reciba el árbol, y que quien no, no lo reciba.
"""

from importlib import reload

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import clear_url_caches

import config.urls

User = get_user_model()

ADMIN = "panel-notas"
ARBOL = f"/{ADMIN}/api/main/pages/?child_of=root&for_explorer=1"


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


@pytest.mark.django_db
def test_el_arbol_responde_a_quien_ya_entro_al_admin(admin_montado):
    staff = User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
    client = Client()
    # force_login: ver el comentario sobre axes en tests/api/test_admin.py.
    client.force_login(staff)

    resp = client.get(ARBOL)

    assert resp.status_code == 200, resp.content[:200]
    assert "items" in resp.json()


@pytest.mark.django_db
def test_el_arbol_no_responde_a_un_anonimo(admin_montado):
    resp = Client().get(ARBOL)

    assert resp.status_code != 200
    assert resp.status_code in (301, 302, 403)


@pytest.mark.django_db
def test_el_arbol_no_responde_a_un_usuario_sin_acceso_al_admin(admin_montado):
    """Estar logueado no alcanza: hace falta el permiso del admin.

    Es la mitad que importa del cambio. Si al sacar `HasAccount` de esta vista
    quedara accesible para cualquier sesión, el árbol de páginas —con títulos y
    estados de borradores sin publicar— sería legible por cualquier usuario
    autenticado.
    """
    cualquiera = User.objects.create_user("comun", "c@x.com", "pw-de-test-12345")
    client = Client()
    client.force_login(cualquiera)

    resp = client.get(ARBOL)

    assert resp.status_code != 200
    assert resp.status_code in (301, 302, 403)


@pytest.mark.django_db
def test_la_api_publica_del_cms_sigue_sin_pedir_autenticacion():
    """El cambio no debe tocar la API que consume la web."""
    resp = Client().get("/cms/api/v2/pages/?type=cms.NotePage")

    assert resp.status_code == 200
