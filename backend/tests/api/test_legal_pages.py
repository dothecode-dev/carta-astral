"""Las páginas legales se mudaron a la web; acá sólo queda la redirección.

El contenido de los documentos (que mencionen el hash del borrado, Anthropic,
RevenueCat y el disclaimer de no-consejo) lo verifica `web/scripts/check-legal.mjs`,
que corre como gate en el mismo CI.
"""

import pytest
from rest_framework.test import APIClient

WEB = "https://astra.dothecode.com"


@pytest.mark.django_db
@pytest.mark.parametrize("doc", ["privacy", "terms"])
def test_redirige_a_la_web_sin_auth(doc):
    resp = APIClient().get(f"/legal/{doc}")
    assert resp.status_code == 302
    assert resp.headers["Location"] == f"{WEB}/es/legal/{doc}"


@pytest.mark.django_db
@pytest.mark.parametrize("lang", ["es", "en", "pt"])
def test_conserva_el_idioma_pedido(lang):
    resp = APIClient().get(f"/legal/privacy?lang={lang}")
    assert resp.headers["Location"] == f"{WEB}/{lang}/legal/privacy"


@pytest.mark.django_db
def test_lang_invalida_cae_a_espanol():
    # Las versiones instaladas de la app mandan el idioma en la query; si llega
    # algo que la web no tiene como ruta, redirigir ahí sería un 404.
    resp = APIClient().get("/legal/terms?lang=de")
    assert resp.headers["Location"] == f"{WEB}/es/legal/terms"


@pytest.mark.django_db
def test_base_url_configurable_por_entorno(settings, monkeypatch):
    # El dominio es provisional: cuando cambie, se cambia por env y no por deploy.
    monkeypatch.setenv("WEB_BASE_URL", "https://ejemplo.test")
    import importlib

    from api import legal

    importlib.reload(legal)
    try:
        assert legal.WEB_BASE_URL == "https://ejemplo.test"
    finally:
        monkeypatch.delenv("WEB_BASE_URL")
        importlib.reload(legal)
