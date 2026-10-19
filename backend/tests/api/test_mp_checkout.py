"""`POST /api/checkout/` en pesos: abre una preferencia de Mercado Pago.

El cliente HTTP de MP es un doble que guarda el cuerpo; Stripe es otro doble
que falla si lo llaman, salvo en el test que prueba justamente que USD sigue
yendo a Stripe.
"""

import pytest

from api import stripe_client
from api.models import Cupon, PasarelaCheckout
from api.pasarelas import mercadopago, mercadopago_api

# El precio en pesos es el real del catálogo ($ 25.000), no el de prueba del conftest.
pytestmark = [pytest.mark.django_db, pytest.mark.catalogo_real]

URL = "/api/checkout/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.COBRO_ARS_ENABLED = True
    settings.MP_ACCESS_TOKEN = "APP_USR-de-prueba"
    settings.MP_RETORNO_URL = "https://astraguia.com/{locale}/compra?checkout_id={checkout_id}"
    settings.MP_NOTIFICACION_URL = "https://api.astraguia.com/api/webhooks/mercadopago/"


@pytest.fixture
def mp(monkeypatch):
    pedidos = []

    def crear(cuerpo):
        pedidos.append(cuerpo)
        return {"id": "pref-123", "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-123"}

    monkeypatch.setattr(mercadopago_api, "crear_preferencia", crear)
    return pedidos


@pytest.fixture
def stripe_prohibido(monkeypatch):
    def _no(*a, **k):
        raise AssertionError("no debía llamar a Stripe")

    monkeypatch.setattr(stripe_client, "crear_checkout", _no)


def test_ars_con_flag_apagado_es_400(account_client, settings, mp, stripe_prohibido):
    settings.COBRO_ARS_ENABLED = False

    r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars"})

    assert r.status_code == 400
    assert r.json()["motivo"] == "moneda_invalida"
    assert mp == []
    assert PasarelaCheckout.objects.count() == 0


def test_ars_con_cupon_es_400_motivo_cupon_no_disponible_en_pesos(account_client, mp, stripe_prohibido):
    Cupon.objects.create(
        codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=10,
        stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1",
    )
    Cupon.objects.create(codigo="GRATIS", porcentaje=100, productos=["informe_natal"], usos_maximos=10)

    for codigo in ("promo30", "gratis"):
        r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars", "cupon": codigo})
        assert r.status_code == 400
        assert r.json() == {"error": "el cupón no sirve", "motivo": "cupon_no_disponible_en_pesos"}
    assert mp == []
    assert PasarelaCheckout.objects.count() == 0


def test_ars_abre_preferencia_con_cada_campo_de_rf8(account_client, mp, stripe_prohibido):
    r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars", "locale": "pt"})

    assert r.status_code == 200, r.content
    (c,) = mp
    (item,) = c["items"]
    assert item == {
        "id": "informe_natal", "title": "Relatório natal ASTRA", "quantity": 1,
        "currency_id": "ARS", "unit_price": 25000.0,
    }
    cid = c["external_reference"]
    assert cid.startswith("mp_") and len(cid) == 35
    assert c["payment_methods"] == {"excluded_payment_types": [{"id": "ticket"}, {"id": "atm"}], "installments": 1}
    assert c["auto_return"] == "approved"
    destino = f"https://astraguia.com/pt/compra?checkout_id={cid}"
    assert c["back_urls"] == {"success": destino, "pending": destino, "failure": destino}
    assert c["notification_url"] == "https://api.astraguia.com/api/webhooks/mercadopago/"
    assert c["expires"] is True
    assert c["expiration_date_from"] < c["expiration_date_to"]
    assert c["expiration_date_to"].endswith(("+00:00", "Z"))
    assert c["metadata"] == {"checkout_id": cid, "account_id": str(account_client.account.pk)}
    assert "payer" not in c


def test_ars_con_carta_manda_el_sujeto_en_la_metadata(account_client, mp, stripe_prohibido, make_chart):
    carta = make_chart(account=account_client.account)

    r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars", "chart_id": str(carta.uuid)})

    assert r.status_code == 200, r.content
    fila = PasarelaCheckout.objects.get()
    assert fila.sujeto_id is not None
    # Como en Stripe: el uuid del sujeto, no el id interno.
    assert mp[0]["metadata"]["sujeto_id"] == str(fila.sujeto.uuid)


def test_el_titulo_cae_al_codigo_si_no_hay_nombre():
    assert mercadopago.titulo("informe_vinculo", "es") == "informe_vinculo"
    assert mercadopago.titulo("informe_natal", "en") == "ASTRA natal chart report"


def test_ars_crea_fila_mercadopago_con_precio_congelado(account_client, mp, stripe_prohibido):
    r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars", "locale": "en"})

    assert r.status_code == 200
    url = "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-123"
    assert r.json() == {"url": url}
    fila = PasarelaCheckout.objects.get()
    assert fila.checkout_id == mp[0]["external_reference"]
    assert fila.pasarela == PasarelaCheckout.MERCADOPAGO
    assert fila.mp_preferencia_id == "pref-123"
    assert fila.url == url
    assert fila.precio_centavos == 2500000
    assert fila.descuento_centavos == 0
    assert fila.moneda == "ars"
    assert fila.locale == "en"
    assert fila.account == account_client.account
    assert fila.codigo_producto == "informe_natal"


def test_ars_cuenta_checkout_abierto(account_client, mp, monkeypatch):
    contados = []
    monkeypatch.setattr(mercadopago, "contar", contados.append)

    account_client.post(URL, {"producto": "informe_natal", "moneda": "ars"})

    assert contados == ["checkout_abierto"]


def test_usd_sigue_yendo_a_stripe(account_client, mp, monkeypatch, settings):
    llamadas = []

    def crear(*a, **k):
        llamadas.append(k)
        return "cs_test_1", "https://checkout.stripe.com/c/pay/cs_test_1"

    monkeypatch.setattr(stripe_client, "crear_checkout", crear)

    r = account_client.post(URL, {"producto": "informe_natal"})

    assert r.status_code == 200
    assert len(llamadas) == 1 and llamadas[0]["moneda"] == "usd"
    assert mp == []
    assert PasarelaCheckout.objects.get().pasarela == PasarelaCheckout.STRIPE


@pytest.mark.parametrize("exc", [mercadopago_api.MPError("x", status=500), mercadopago_api.MPNoConfigurado("x")])
def test_mp_caido_responde_503_y_no_crea_fila(account_client, monkeypatch, exc):
    def _cae(cuerpo):
        raise exc

    monkeypatch.setattr(mercadopago_api, "crear_preferencia", _cae)

    r = account_client.post(URL, {"producto": "informe_natal", "moneda": "ars"})

    assert r.status_code == 503
    assert PasarelaCheckout.objects.count() == 0
