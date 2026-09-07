"""`checkout.session.expired`: una sesión que venció sin pagarse.

Antes el webhook la ignoraba y la fila quedaba abierta para siempre; la cuenta
la mostraba como «Procesando el pago…» hasta que un corte por fecha la
escondía. Ahora el evento marca la fila como vencida. No mueve plata: no hay
nada que acreditar ni que devolver, y por eso tampoco consulta a Stripe.
"""

import json

import pytest
from django.utils import timezone

from api import webhooks_stripe
from api.models import CuponUso, Derecho, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
PRECIO = "price_natal"
SESSION = "cs_test_vence"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {PRECIO: "informe_natal"}


def _postear(client, tipo, session_id=SESSION):
    cuerpo = json.dumps({
        "id": "evt_1", "type": tipo,
        "data": {"object": {"id": session_id, "object": "checkout.session"}},
    }).encode()
    return client.post(
        URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


def _vencer(client, session_id=SESSION):
    return _postear(client, "checkout.session.expired", session_id)


@pytest.fixture
def abierta(make_account):
    return PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=make_account(), codigo_producto="informe_natal",
        url="https://checkout.stripe.com/c/pay/" + SESSION,
    )


def test_una_sesion_abierta_queda_vencida(client, abierta):
    assert _vencer(client).status_code == 200

    abierta.refresh_from_db()
    assert abierta.vencido_at is not None
    assert abierta.acreditado_at is None


def test_el_mismo_evento_dos_veces_deja_una_sola_marca(client, abierta):
    _vencer(client)
    abierta.refresh_from_db()
    primera = abierta.vencido_at

    assert _vencer(client).status_code == 200
    abierta.refresh_from_db()
    assert abierta.vencido_at == primera


def test_una_sesion_ya_acreditada_no_se_toca(client, abierta):
    """Stripe no vence una sesión pagada; si el evento llegara igual, la plata
    ya entró y manda: la compra sigue siendo una compra."""
    PasarelaCheckout.objects.filter(pk=abierta.pk).update(acreditado_at=timezone.now())

    assert _vencer(client).status_code == 200

    abierta.refresh_from_db()
    assert abierta.vencido_at is None
    assert abierta.acreditado_at is not None


def test_sin_fila_para_esa_sesion_responde_200_y_no_crea_nada(client):
    """Definitivo, no transitorio: reintentar no va a hacer aparecer la fila."""
    assert _vencer(client, "cs_de_otro_sistema").status_code == 200
    assert not PasarelaCheckout.objects.exists()


def test_vencer_no_mueve_plata(client, abierta):
    _vencer(client)

    assert not Movimiento.objects.exists()
    assert not Derecho.objects.filter(account=abierta.account).exists()
    assert not CuponUso.objects.exists()


def test_un_pago_que_llega_despues_del_vencimiento_acredita_igual(client, monkeypatch, abierta):
    """El orden de entrega de Stripe no está garantizado. Si la fila ya quedó
    vencida y después llega el `completed` con `paid`, la plata entró: se
    acredita como siempre."""
    _vencer(client)

    def falsa(session_id):
        return {
            "id": SESSION, "payment_status": "paid", "amount_subtotal": 2900,
            "amount_total": 2900, "total_details": {"amount_tax": 0, "amount_discount": 0},
            "payment_intent": "pi_1", "metadata": {},
            "line_items": {"data": [{"price": {"id": PRECIO}, "quantity": 1}]},
        }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", falsa)

    assert _postear(client, "checkout.session.completed").status_code == 200

    abierta.refresh_from_db()
    assert abierta.acreditado_at is not None
    assert Derecho.objects.get(account=abierta.account, codigo_producto="informe_natal").cantidad_restante == 1
