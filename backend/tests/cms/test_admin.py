"""El admin del CMS no está donde los bots lo buscan, y sin env var no existe.

Mismo patrón que `ADMIN_URL` en `config/urls.py`, que ya estaba en el repo.

`config.urls` arma `urlpatterns` una sola vez, al importarse, leyendo
`WAGTAIL_ADMIN_URL` del entorno. Para probar el montaje condicional hay que
recargar el módulo con el entorno modificado. Eso muta un módulo global
(y el resolver de URLs, que cachea por `ROOT_URLCONF`), así que cada test
usa `monkeypatch.context()` para acotar el cambio de entorno y, pase lo que
pase, vuelve a recargar el módulo al final para dejarlo consistente con el
entorno real y no ensuciar los tests que corran después en la misma sesión.
"""
from importlib import reload

import pytest
from django.test import Client
from django.urls import clear_url_caches

import config.urls


def _reload_urls() -> None:
    reload(config.urls)
    clear_url_caches()


@pytest.mark.django_db
def test_sin_variable_el_admin_no_se_monta(monkeypatch):
    try:
        with monkeypatch.context() as m:
            m.delenv("WAGTAIL_ADMIN_URL", raising=False)
            _reload_urls()
            assert Client().get("/cms-admin/").status_code == 404
    finally:
        # El context ya restauró el entorno real; recargamos para que el
        # módulo (y el resolver) reflejen ese entorno, no el del test.
        _reload_urls()


@pytest.mark.django_db
def test_con_variable_pide_login(monkeypatch):
    try:
        with monkeypatch.context() as m:
            m.setenv("WAGTAIL_ADMIN_URL", "panel-notas")
            _reload_urls()
            resp = Client().get("/panel-notas/")
            # Wagtail manda al login: 302, nunca 200 sin sesión.
            assert resp.status_code in (301, 302)
            assert "login" in resp.headers["Location"]
    finally:
        _reload_urls()
