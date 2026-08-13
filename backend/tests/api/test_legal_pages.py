"""Las páginas legales se mudaron a la web; acá sólo queda la redirección.

El contenido de los documentos (que mencionen el hash del borrado, Anthropic,
RevenueCat y el disclaimer de no-consejo) lo verifica `web/scripts/check-legal.mjs`,
que corre como gate en el mismo CI.
"""

import pytest
from rest_framework.test import APIClient

WEB = "https://ejemplo.test"


@pytest.fixture(autouse=True)
def web_base_url(settings):
    """El destino sale de `settings`, así que se fija desde ahí.

    Antes estos tests afirmaban un dominio concreto porque `api.legal` leía la
    variable de entorno por su cuenta, con un default hardcodeado: el test
    pasaba justamente cuando el módulo mandaba al dominio equivocado.
    """
    settings.WEB_BASE_URL = WEB


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
def test_sigue_a_settings_sin_reimportar(settings):
    # El dominio ya cambió una vez y puede volver a cambiar. Se toma en cada
    # request: antes vivía en una constante de módulo y hacía falta recargarlo.
    settings.WEB_BASE_URL = "https://otro.test"
    resp = APIClient().get("/legal/privacy")
    assert resp.headers["Location"] == "https://otro.test/es/legal/privacy"


@pytest.mark.django_db
def test_no_duplica_la_barra_final(settings):
    settings.WEB_BASE_URL = "https://ejemplo.test/"
    resp = APIClient().get("/legal/privacy")
    assert resp.headers["Location"] == "https://ejemplo.test/es/legal/privacy"
