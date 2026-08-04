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


def test_se_instala_el_modulo_de_documentos():
    # Decisión revisada 2026-08-04 (spec RF6): antes iba excluido por el
    # riesgo de XSS de un documento servible desde el mismo host que la API.
    # Se instala igual porque, sin él, el admin de Wagtail no arranca:
    # `wagtailadmin_tags.wagtail_config` reversea su API incondicionalmente
    # (`wagtailadmin_api:documents:listing`), y sin el módulo esa ruta no
    # existe -> 500 en cualquier página del panel, login incluido
    # (reproducido, no supuesto). Riesgo aceptado por Gustavo: un solo
    # editor, sin más gente con acceso al panel. No lo vuelvas a sacar sin
    # resolver antes ese 500.
    assert apps.is_installed("wagtail.documents")


def test_el_healthcheck_sigue_sin_tocar_la_base(client):
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
