"""Cambiar un precio con sesiones de pago abiertas.

Una sesión de Stripe vive una hora y cobra el precio con el que se abrió. Si el
catálogo cambia en esa hora, el webhook tiene que acreditar contra el precio
de la sesión y no contra el nuevo: si no, cobra y no entrega nada.
"""

import dataclasses
import json

import pytest

from api import catalogo, stripe_client, webhooks_stripe
from api.models import Movimiento
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

SESSION = "cs_test_precio"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    settings.STRIPE_SUCCESS_URL = (
        "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"
    )


@pytest.fixture
def stripe_abre(monkeypatch):
    class _Sesion:
        id = SESSION
        url = "https://checkout.stripe.com/c/pay/cs_test_precio"

    monkeypatch.setattr(
        stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **p: _Sesion()),
    )


def _cambiar_precio(monkeypatch, centavos):
    monkeypatch.setitem(
        catalogo.CATALOGO, "informe_natal",
        dataclasses.replace(catalogo.CATALOGO["informe_natal"], precio_centavos=centavos),
    )


def _stripe_avisa_el_pago(client, monkeypatch, subtotal):
    sesion = {
        "id": SESSION, "payment_status": "paid",
        "amount_subtotal": subtotal, "amount_total": subtotal,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _id: sesion)
    cuerpo = json.dumps({
        "id": "evt_1", "type": "checkout.session.completed",
        "data": {"object": {"id": SESSION, "object": "checkout.session"}},
    }).encode()
    return client.post(
        "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


def _acreditada():
    return Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").exists()


def test_la_sesion_abierta_antes_del_cambio_se_acredita_a_su_precio(
    account_client, client, stripe_abre, monkeypatch,
):
    _cambiar_precio(monkeypatch, 2900)
    assert account_client.post("/api/checkout/", {"producto": "informe_natal"}).status_code == 200

    _cambiar_precio(monkeypatch, 500)

    assert _stripe_avisa_el_pago(client, monkeypatch, 2900).status_code == 200
    assert _acreditada()


def test_el_precio_congelado_no_acepta_cualquier_monto(
    account_client, client, stripe_abre, monkeypatch,
):
    """Congelar el precio no abre la puerta a montos que nadie fijó."""
    _cambiar_precio(monkeypatch, 2900)
    account_client.post("/api/checkout/", {"producto": "informe_natal"})
    _cambiar_precio(monkeypatch, 500)

    _stripe_avisa_el_pago(client, monkeypatch, 500)

    assert not _acreditada()


def test_un_precio_retirado_se_sigue_acreditando(
    account_client, client, stripe_abre, monkeypatch, settings,
):
    """El precio viejo sale de `STRIPE_PRECIOS` —con él ya no se vende— pero
    una sesión abierta con él todavía puede pagarse durante una hora."""
    _cambiar_precio(monkeypatch, 2900)
    account_client.post("/api/checkout/", {"producto": "informe_natal"})
    _cambiar_precio(monkeypatch, 500)
    settings.STRIPE_PRECIOS = {"price_nuevo": "informe_natal"}
    settings.STRIPE_PRECIOS_RETIRADOS = {"price_natal": "informe_natal"}

    assert _stripe_avisa_el_pago(client, monkeypatch, 2900).status_code == 200
    assert _acreditada()


def test_con_dos_precios_a_la_venta_para_un_producto_no_se_abre_el_pago(
    account_client, stripe_abre, settings,
):
    """Con dos ids para el mismo producto, el checkout elegía el primero del
    mapeo: si era el viejo, cobraba US$ 29 contra un catálogo de 5 y el
    webhook rechazaba la compra ya cobrada. Mejor no abrir el pago."""
    settings.STRIPE_PRECIOS = {"price_viejo": "informe_natal", "price_nuevo": "informe_natal"}

    r = account_client.post("/api/checkout/", {"producto": "informe_natal"})

    assert r.status_code == 503
