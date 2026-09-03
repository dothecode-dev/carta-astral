"""La acreditación de una compra de Stripe: tests 6-16 y 36-38 de la spec.

Por acá entra la plata. Dos reglas de fondo que no están en el código de Polar
y son la diferencia con esta pasarela:

- **Se acredita sólo con `payment_status == "paid"`**, lista blanca y no lista
  negra: el tercer valor, `no_payment_required`, aparece con un cupón del 100%
  y con una lista negra acreditaría un informe sin haber cobrado nada.
- **Un fallo transitorio se responde 5xx.** Stripe reintenta tres días y no
  deshabilita el endpoint, así que una compra que falla al acreditar se
  recupera sola. Con Polar era al revés: 2xx a todo y el error se perdía.
"""

import json

import pytest

from api import webhooks_stripe
from api.canje import MontoInvalido
from api.models import Derecho, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
PRECIO = "price_natal"
SESSION = "cs_test_compra"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {PRECIO: "informe_natal"}


def _sesion(**cambios) -> dict:
    """Lo que devuelve la API al re-consultar la sesión, con line_items."""
    sesion = {
        "id": SESSION,
        "payment_status": "paid",
        "amount_subtotal": 2900,
        "amount_total": 2900,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1",
        "metadata": {},
        "line_items": {"data": [{"price": {"id": PRECIO}, "quantity": 1}]},
    }
    sesion.update(cambios)
    return sesion


def _entregar(client, monkeypatch, sesion=None, tipo="checkout.session.completed", error=None):
    def falsa(session_id):
        assert session_id == SESSION
        if error is not None:
            raise error
        return sesion if sesion is not None else _sesion()

    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", falsa)
    cuerpo = json.dumps({
        "id": "evt_1", "type": tipo,
        "data": {"object": {"id": SESSION, "object": "checkout.session"}},
    }).encode()
    return client.post(
        URL, data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


@pytest.fixture
def compra(make_account, make_chart):
    cuenta = make_account()
    return PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )


def _restante(codigo="informe_natal"):
    d = Derecho.objects.filter(codigo_producto=codigo).first()
    return None if d is None else d.cantidad_restante


# --- Acreditación -----------------------------------------------------------

def test_una_sesion_pagada_otorga_una_vez(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1


def test_la_misma_entrega_dos_veces_otorga_una_sola(client, monkeypatch, compra):
    _entregar(client, monkeypatch)
    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1


def test_una_sesion_sin_pagar_no_otorga(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, _sesion(payment_status="unpaid"))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_el_pago_asincrono_posterior_si_otorga(client, monkeypatch, compra):
    _entregar(client, monkeypatch, _sesion(payment_status="unpaid"))

    r = _entregar(client, monkeypatch, tipo="checkout.session.async_payment_succeeded")

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1


def test_no_payment_required_no_otorga(client, monkeypatch, compra):
    """El estado que produce un cupón del 100%. Lista blanca: no acredita."""
    r = _entregar(client, monkeypatch, _sesion(payment_status="no_payment_required"))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_un_subtotal_distinto_al_catalogo_no_otorga(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, _sesion(amount_subtotal=100, amount_total=100))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_un_comprador_con_impuesto_encima_igual_acredita(client, monkeypatch, compra, caplog):
    """El precio quedó en `exclusive`: el comprador pagó 3016 y el subtotal
    sigue siendo 2900. Se acredita —cobró de más, no de menos— y queda el log
    que delata al precio mal configurado."""
    r = _entregar(client, monkeypatch, _sesion(
        amount_total=3016, total_details={"amount_tax": 116, "amount_discount": 0},
    ))

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1
    assert "3016" in caplog.text and "2900" in caplog.text


def test_un_subtotal_nulo_no_se_disfraza_de_monto_invalido(client, monkeypatch, compra, caplog):
    r = _entregar(client, monkeypatch, _sesion(amount_subtotal=None))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()
    assert "sin monto" in caplog.text


def test_un_precio_que_no_mapeamos_no_otorga(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, _sesion(
        line_items={"data": [{"price": {"id": "price_desconocido"}, "quantity": 1}]},
    ))

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_si_el_producto_del_checkout_no_coincide_no_otorga(client, monkeypatch, compra, settings):
    settings.STRIPE_PRECIOS = {PRECIO: "pack_5_natal"}

    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_una_sesion_sin_fila_y_sin_metadata_no_otorga(client, monkeypatch):
    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert not Movimiento.objects.exists()


def test_una_sesion_sin_fila_se_resuelve_por_metadata(client, monkeypatch, make_account):
    cuenta = make_account()

    r = _entregar(client, monkeypatch, _sesion(metadata={"account_id": str(cuenta.pk)}))

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1


# --- Lo que se reintenta ----------------------------------------------------

def test_si_la_consulta_a_stripe_falla_pedimos_reintento(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, error=RuntimeError("la API no responde"))

    assert r.status_code >= 500
    assert not Movimiento.objects.exists()


def test_un_error_inesperado_al_acreditar_pide_reintento(client, monkeypatch, compra):
    def explota(*_a, **_k):
        raise RuntimeError("la base se cayó")

    monkeypatch.setattr(webhooks_stripe, "aplicar_compra", explota)

    r = _entregar(client, monkeypatch)

    assert r.status_code >= 500


def test_un_monto_invalido_no_se_reintenta(client, monkeypatch, compra):
    """Reintentar no lo va a arreglar: se responde 200 y se descarta."""
    def rechaza(*_a, **_k):
        raise MontoInvalido("informe_natal")

    monkeypatch.setattr(webhooks_stripe, "aplicar_compra", rechaza)

    r = _entregar(client, monkeypatch)

    assert r.status_code == 200


# --- La marca que lee la página de retorno ----------------------------------

def test_al_acreditar_se_guardan_el_payment_intent_y_la_marca(client, monkeypatch, compra):
    _entregar(client, monkeypatch)

    compra.refresh_from_db()
    assert compra.payment_intent == "pi_1"
    assert compra.acreditado_at is not None


def test_el_reintento_deja_la_marca_aunque_la_compra_ya_estuviera_aplicada(
    client, monkeypatch, compra,
):
    """La entrega otorgó y falló después, al marcar. En el reintento
    `aplicar_compra` devuelve False, y sin esto la página de retorno diría
    "pendiente" para siempre sobre una compra ya entregada."""
    _entregar(client, monkeypatch)
    PasarelaCheckout.objects.filter(pk=compra.pk).update(acreditado_at=None, payment_intent="")

    _entregar(client, monkeypatch)

    compra.refresh_from_db()
    assert compra.acreditado_at is not None
    assert compra.payment_intent == "pi_1"
