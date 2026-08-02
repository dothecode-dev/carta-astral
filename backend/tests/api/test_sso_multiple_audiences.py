"""Varias credenciales por proveedor: la app y la web no comparten client id.

Google exige un client id por plataforma (Android, iOS, Web) y Apple usa el
bundle id para la app y un Services ID para el sitio. El validador aceptaba uno
solo, así que habilitar la web habría dejado a la app sin poder entrar.
"""

import pytest
from django.test import override_settings

from api import sso


def test_una_sola_credencial_sigue_funcionando():
    with override_settings(GOOGLE_AUD="movil.apps.googleusercontent.com"):
        assert sso.audiences_for("google") == ["movil.apps.googleusercontent.com"]


def test_acepta_varias_separadas_por_coma():
    with override_settings(
        GOOGLE_AUD="android.apps.googleusercontent.com,web.apps.googleusercontent.com"
    ):
        assert sso.audiences_for("google") == [
            "android.apps.googleusercontent.com",
            "web.apps.googleusercontent.com",
        ]


def test_tolera_espacios_alrededor_de_las_comas():
    # Pegar valores en un panel de entorno deja espacios con facilidad.
    with override_settings(APPLE_AUD=" com.cartaastral.app , com.cartaastral.app.web "):
        assert sso.audiences_for("apple") == ["com.cartaastral.app", "com.cartaastral.app.web"]


def test_descarta_entradas_vacias():
    with override_settings(GOOGLE_AUD="uno,,dos,"):
        assert sso.audiences_for("google") == ["uno", "dos"]


def test_sin_configurar_no_hay_audiencias():
    # Fail-closed: sin credenciales el login devuelve 503, no entra cualquiera.
    with override_settings(GOOGLE_AUD=""):
        assert sso.audiences_for("google") == []


@pytest.mark.parametrize("provider", ["apple", "google"])
def test_el_login_sigue_fallando_cerrado_sin_credenciales(provider):
    with override_settings(APPLE_AUD="", GOOGLE_AUD=""):
        validate = sso.validate_apple if provider == "apple" else sso.validate_google
        with pytest.raises(sso.SSONotConfigured):
            validate("cualquier.token.falso")
