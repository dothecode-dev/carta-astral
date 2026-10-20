"""`apertura.abrir_checkout`: el único camino que abre un pago (R8).

Congela precio y descuento, elige la pasarela por la moneda y deja la fila
con la pasarela explícita. Stripe y Mercado Pago son dobles: el de Stripe
reemplaza `stripe_client.crear_checkout`, el de MP `crear_preferencia`.
"""

import pytest

from api import apertura, catalogo, stripe_client
from api.models import Cupon, PasarelaCheckout
from api.pasarelas import mercadopago_api

# Precios reales del catálogo: hay producto en usd, brl y ars.
pytestmark = [pytest.mark.django_db, pytest.mark.catalogo_real]


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.COBRO_ARS_ENABLED = True
    settings.MP_ACCESS_TOKEN = "APP_USR-de-prueba"
    settings.MP_RETORNO_URL = "https://astraguia.com/{locale}/compra?checkout_id={checkout_id}"
    settings.MP_NOTIFICACION_URL = "https://api.astraguia.com/api/webhooks/mercadopago/"


@pytest.fixture
def stripe(monkeypatch):
    llamadas = []

    def crear(*a, **k):
        llamadas.append(k)
        return "cs_test_ap", "https://checkout.stripe.com/c/pay/cs_test_ap"

    monkeypatch.setattr(stripe_client, "crear_checkout", crear)
    return llamadas


@pytest.fixture
def mp(monkeypatch):
    pedidos = []

    def crear(cuerpo):
        pedidos.append(cuerpo)
        return {"id": "pref-ap", "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?pref_id=pref-ap"}

    monkeypatch.setattr(mercadopago_api, "crear_preferencia", crear)
    return pedidos


def test_usd_abre_stripe_y_crea_fila_stripe(account, stripe, mp):
    fila = apertura.abrir_checkout(account, "informe_natal", sujeto=None, locale="es", moneda="usd")

    assert len(stripe) == 1 and stripe[0]["moneda"] == "usd"
    assert mp == []
    assert fila.pasarela == PasarelaCheckout.STRIPE
    assert fila.checkout_id == "cs_test_ap" and fila.url.endswith("cs_test_ap")
    assert fila.account == account and fila.moneda == "usd"
    assert PasarelaCheckout.objects.get() == fila


def test_brl_abre_stripe(account, stripe, mp):
    fila = apertura.abrir_checkout(account, "informe_natal", sujeto=None, locale="pt", moneda="brl")

    assert len(stripe) == 1 and stripe[0]["moneda"] == "brl"
    assert mp == []
    assert fila.pasarela == PasarelaCheckout.STRIPE and fila.moneda == "brl"


def test_ars_abre_mercadopago_con_mail(account, stripe, mp):
    fila = apertura.abrir_checkout(
        account, "informe_natal", sujeto=None, locale="es", moneda="ars", mail="quien@paga.com",
    )

    assert stripe == []
    assert len(mp) == 1 and mp[0]["payer"] == {"email": "quien@paga.com"}
    assert fila.pasarela == PasarelaCheckout.MERCADOPAGO
    assert fila.mail_comprador == "quien@paga.com" and fila.mp_preferencia_id == "pref-ap"


def test_fallo_de_stripe_no_deja_fila(account, monkeypatch):
    def cae(*a, **k):
        raise stripe_client.StripeError("APIConnectionError")

    monkeypatch.setattr(stripe_client, "crear_checkout", cae)

    with pytest.raises(apertura.ERRORES_DE_PASARELA):
        apertura.abrir_checkout(account, "informe_natal", sujeto=None, locale="es", moneda="usd")
    assert not PasarelaCheckout.objects.exists()


def test_precio_y_descuento_congelados_en_la_fila(account, stripe):
    cupon = Cupon.objects.create(
        codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=10,
        stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1",
    )
    precio = catalogo.producto("informe_natal").precio_en("usd")

    fila = apertura.abrir_checkout(
        account, "informe_natal", sujeto=None, locale="es", moneda="usd", cupon=cupon,
    )

    assert stripe[0]["cupon"] == cupon
    assert fila.cupon == cupon
    assert fila.precio_centavos == precio
    assert fila.descuento_centavos == (precio * 30 + 50) // 100
