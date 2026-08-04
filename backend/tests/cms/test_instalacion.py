"""Wagtail entra sin llevarse puesto lo que ya funciona.

El backend está en producción: la app consume esta API hoy. Montar un CMS no
puede cambiar el comportamiento de la API, de los legales ni del healthcheck.
"""
from django.apps import apps


def test_la_app_cms_esta_instalada():
    assert apps.is_installed("cms")


def test_wagtail_esta_instalado():
    assert apps.is_installed("wagtail")
    assert apps.is_installed("wagtail.images")


def test_no_se_instala_el_modulo_de_documentos():
    # Un documento servible desde el mismo host que la API es XSS almacenado
    # sobre ese origen (RF6).
    assert not apps.is_installed("wagtail.documents")


def test_el_healthcheck_sigue_sin_tocar_la_base(client):
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
