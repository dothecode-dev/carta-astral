"""El checkout con un cupón parcial (1..99 %): el descuento lo aplica Stripe.

Del navegador llega el código; acá se valida, se congela el descuento en la
fila y se abre la sesión con el Promotion Code. Medido en sandbox el 06-09:
Stripe rechaza la creación de la sesión con un promo agotado con
`InvalidRequestError(code="coupon_expired", param="discounts[0][...]")`.
"""
import logging

import pytest

from api import stripe_client
from api.models import Cupon, PasarelaCheckout

pytestmark = pytest.mark.django_db

URL = "/api/checkout/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"


@pytest.fixture
def stripe_responde(monkeypatch):
    pedidos = []

    class _Sesion:
        def __init__(self, n):
            # Un id por sesión: `checkout_id` es único, y un test que abre dos
            # checkouts seguidos chocaría con la constraint, no con lo que prueba.
            self.id = "cs_test_cupon" if n == 0 else f"cs_test_cupon_{n}"
            self.url = f"https://checkout.stripe.com/c/pay/{self.id}"

    def crear(**params):
        pedidos.append(params)
        return _Sesion(len(pedidos) - 1)

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(crear))
    return pedidos


@pytest.fixture
def promo():
    return Cupon.objects.create(
        codigo="PROMO30", porcentaje=30, productos=["informe_natal", "pack_5_natal"], usos_maximos=10,
        stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1",
    )


def test_el_descuento_viaja_como_promotion_code_y_el_precio_sigue_siendo_el_del_catalogo(
    account_client, stripe_responde, promo,
):
    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "promo30"})

    assert r.status_code == 200, r.content
    (enviado,) = stripe_responde
    assert enviado["discounts"] == [{"promotion_code": "promo_1"}]
    assert enviado["line_items"] == [{"price": "price_natal", "quantity": 1}]
    assert enviado["managed_payments"] == {"enabled": True}


def test_el_descuento_queda_congelado_en_la_fila(account_client, stripe_responde, promo):
    account_client.post(URL, {"producto": "pack_5_natal", "cupon": "PROMO30"})

    fila = PasarelaCheckout.objects.get(checkout_id="cs_test_cupon")
    assert fila.cupon == promo
    assert fila.descuento_centavos == 3750  # 30 % de 12500


def test_sin_cupon_no_se_manda_discounts_ni_queda_descuento(account_client, stripe_responde):
    account_client.post(URL, {"producto": "informe_natal"})

    assert "discounts" not in stripe_responde[0]
    fila = PasarelaCheckout.objects.get(checkout_id="cs_test_cupon")
    assert (fila.cupon, fila.descuento_centavos) == (None, 0)


def test_nunca_se_manda_allow_promotion_codes(account_client, stripe_responde, promo):
    """Es la puerta por la que entra un descuento que nuestra base no conoce
    y que `amount_subtotal` no refleja: cerrada por test, no por prosa."""
    account_client.post(URL, {"producto": "informe_natal", "cupon": "PROMO30"})
    account_client.post(URL, {"producto": "informe_natal"})

    for enviado in stripe_responde:
        assert "allow_promotion_codes" not in enviado


def test_un_cupon_que_no_abarca_el_producto_no_abre_el_checkout(account_client, stripe_responde):
    Cupon.objects.create(codigo="SOLOPACK", porcentaje=30, productos=["pack_5_natal"], usos_maximos=10,
                         stripe_promotion_code_id="promo_2")

    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "SOLOPACK"})

    assert (r.status_code, r.json()["motivo"]) == (400, "no_aplica")
    assert stripe_responde == []
    assert PasarelaCheckout.objects.count() == 0


def test_si_stripe_rechaza_el_promo_se_responde_agotado_y_no_queda_fila(
    account_client, monkeypatch, promo, caplog,
):
    def rechaza(**params):
        raise stripe_client.stripe.InvalidRequestError(
            "Coupon cup_1 is expired and cannot be applied.",
            "discounts[0][promotion_code][coupon]", code="coupon_expired",
        )

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(rechaza))

    with caplog.at_level(logging.WARNING):
        r = account_client.post(URL, {"producto": "informe_natal", "cupon": "PROMO30"})

    assert (r.status_code, r.json()["motivo"]) == (400, "agotado")
    assert PasarelaCheckout.objects.count() == 0
    assert any("PROMO30" in m and "stripe" in m.lower() for m in caplog.messages)


def test_otro_error_de_stripe_sigue_siendo_502(account_client, monkeypatch, promo):
    def explota(**params):
        raise stripe_client.stripe.InvalidRequestError("No such price", "line_items[0][price]")

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(explota))

    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "PROMO30"})

    assert r.status_code == 502
    assert PasarelaCheckout.objects.count() == 0
