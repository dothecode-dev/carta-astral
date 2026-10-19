"""`POST /api/checkout/anonimo/` en pesos: el mail se pide ANTES de pagar.

MP no devuelve el mail de quien pagó (es el de la cuenta de MP, que puede ser
de un pariente), así que el formulario lo junta y queda en `mail_comprador`.
"""

import pytest
from django.core.cache import cache

from api import identity, stripe_client
from api.models import Chart, PasarelaCheckout
from api.pasarelas import mercadopago_api

pytestmark = [pytest.mark.django_db, pytest.mark.catalogo_real]
URL = "/api/checkout/anonimo/"
DATOS = {"date": "1990-05-10", "time": "14:30", "time_known": True, "lat": -34.6, "lng": -58.4,
         "place_label": "Buenos Aires, AR", "locale": "es"}


@pytest.fixture(autouse=True)
def _configurado(settings):
    cache.clear()
    settings.COBRO_ARS_ENABLED = True
    settings.MP_ACCESS_TOKEN = "APP_USR-de-prueba"
    settings.MP_RETORNO_URL = "https://astraguia.com/{locale}/compra?checkout_id={checkout_id}"
    settings.MP_NOTIFICACION_URL = "https://api.astraguia.com/api/webhooks/mercadopago/"
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"
    yield
    cache.clear()


@pytest.fixture
def mp(monkeypatch):
    pedidos = []

    def crear(cuerpo):
        pedidos.append(cuerpo)
        return {"id": "pref-9", "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-9"}

    monkeypatch.setattr(mercadopago_api, "crear_preferencia", crear)
    return pedidos


@pytest.fixture
def stripe_prohibido(monkeypatch):
    def _no(*a, **k):
        raise AssertionError("no debía llamar a Stripe")

    monkeypatch.setattr(stripe_client, "crear_checkout", _no)


def _post(client, cuerpo):
    return client.post(URL, cuerpo, content_type="application/json")


@pytest.mark.parametrize("email", [None, "", "no-es-un-mail", 123])
def test_ars_sin_email_es_400(client, mp, stripe_prohibido, email):
    cuerpo = {**DATOS, "moneda": "ars"}
    if email is not None:
        cuerpo["email"] = email

    r = _post(client, cuerpo)

    assert r.status_code == 400
    assert r.json()["motivo"] == "email_invalido"
    assert mp == [] and PasarelaCheckout.objects.count() == 0 and Chart.objects.count() == 0


def test_ars_guarda_mail_comprador_y_nonce(client, mp, stripe_prohibido):
    r = _post(client, {**DATOS, "moneda": "ars", "email": "  Ana@Example.COM "})

    assert r.status_code == 200
    cuerpo = r.json()
    fila = PasarelaCheckout.objects.get(checkout_id=cuerpo["checkout_id"])
    assert fila.pasarela == PasarelaCheckout.MERCADOPAGO
    assert fila.mail_comprador == "ana@example.com"
    assert fila.anonimo and fila.account is None
    assert fila.nonce_hash == identity.hash_token(cuerpo["nonce"])
    assert fila.url == cuerpo["url"] and "mercadopago" in cuerpo["url"]
    assert mp[0]["payer"] == {"email": "ana@example.com"}


def test_ars_crea_carta_y_preferencia_en_el_mismo_atomo(client, monkeypatch, stripe_prohibido):
    def falla(cuerpo):
        raise mercadopago_api.MPError("boom")

    monkeypatch.setattr(mercadopago_api, "crear_preferencia", falla)

    r = _post(client, {**DATOS, "moneda": "ars", "email": "ana@example.com"})

    assert r.status_code == 503
    assert Chart.objects.count() == 0 and PasarelaCheckout.objects.count() == 0


def test_ars_sin_configurar_es_503(client, settings, stripe_prohibido):
    settings.MP_ACCESS_TOKEN = ""
    r = _post(client, {**DATOS, "moneda": "ars", "email": "ana@example.com"})
    assert r.status_code == 503
    assert Chart.objects.count() == 0


def test_ars_con_el_flag_apagado_es_400_sin_llamar_a_mp(client, settings, mp, stripe_prohibido):
    settings.COBRO_ARS_ENABLED = False

    r = _post(client, {**DATOS, "moneda": "ars", "email": "ana@example.com"})

    assert r.status_code == 400
    assert mp == [] and PasarelaCheckout.objects.count() == 0 and Chart.objects.count() == 0


def test_usd_sin_email_sigue_como_hoy(client, monkeypatch, mp):
    class _Sesion:
        id = "cs_test_1"
        url = "https://checkout.stripe.com/c/pay/cs_test_1"

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **p: _Sesion()))

    r = _post(client, {**DATOS, "moneda": "usd"})

    assert r.status_code == 200
    fila = PasarelaCheckout.objects.get()
    assert fila.pasarela == PasarelaCheckout.STRIPE and fila.mail_comprador == ""
    assert mp == []
