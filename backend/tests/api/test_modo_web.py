"""Modo web: la superficie que existe sólo para la app móvil queda apagada.

La app no se retoma por ahora y lo que se termina es la web, así que el login
de Apple y el webhook de compras in-app no se exponen. Nada se borra: son dos
flags de entorno, apagados por defecto, que se vuelven a prender cuando la app
vuelva. El fail-closed que ya existía (401 sin `REVENUECAT_WEBHOOK_AUTH`, 503
sin `APPLE_AUD`) sigue siendo la defensa real; esto es la decisión escrita.

Los dos flags son independientes a propósito: lo más probable es que la app
vuelva por una plataforma antes que por la otra.
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api.models import Account, Session


@pytest.mark.django_db
def test_el_webhook_de_iap_responde_503_cuando_esta_apagado(client):
    """503 y no 404: un 404 le dice al proveedor que el endpoint no existe y
    varios desactivan el webhook tras unas cuantas respuestas así. El 503 con
    `Retry-After` dice "ahora no" y deja el reintento en pie."""
    resp = client.post(
        "/api/webhooks/revenuecat", data="{}", content_type="application/json"
    )

    assert resp.status_code == 503
    assert resp.headers["Retry-After"]


@pytest.mark.django_db
def test_el_login_de_apple_responde_404_cuando_esta_apagado(client):
    """404 y no 503, al revés que el webhook: acá no hay ningún sistema
    externo reintentando, así que conviene no anunciar que la ruta existe."""
    resp = client.post(
        "/api/auth/apple", data="{}", content_type="application/json"
    )

    assert resp.status_code == 404


@pytest.mark.django_db
def test_mint_dev_session_se_niega_a_correr_sin_debug(settings):
    """El comando emite un token de sesión válido saltándose el SSO. La guarda
    por DEBUG ya existía; lo que faltaba era que alguien la sostuviera: sin
    este test, borrarla no rompe nada y el token queda al alcance de cualquiera
    que pueda correr un comando en el contenedor de producción."""
    settings.DEBUG = False

    with pytest.raises(CommandError):
        call_command("mint_dev_session")

    assert Account.objects.count() == 0
    assert Session.objects.count() == 0


def test_los_flags_de_la_superficie_app_vienen_apagados(settings):
    """Sin variables de entorno, apagados. Si alguien deja un
    `APP_AUTH_ENABLED=1` colgado en el entorno de CI, esto lo delata."""
    assert settings.APP_AUTH_ENABLED is False
    assert settings.IAP_WEBHOOK_ENABLED is False


@pytest.mark.django_db
def test_el_login_de_google_sigue_vivo_con_la_superficie_app_apagada(client):
    """Google es el login de la web (`GoogleSignIn.tsx`): apagar la superficie
    de la app no puede llevárselo puesto. 400 por falta de `id_token` es la
    respuesta viva; un 404 significaría que la guarda se fue de rango."""
    resp = client.post(
        "/api/auth/google", data="{}", content_type="application/json"
    )

    assert resp.status_code == 400
