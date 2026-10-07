"""Una cuenta con deuda que paga: la unidad salda la deuda y no hay informe que canjear.
Antes de este arreglo (spec pagar-es-entrar RF5b), el canje fallaba por falta de
derecho, el átomo se revertía y el webhook quedaba en 5xx los tres días de
reintentos: plata cobrada y nunca acreditada."""

import json

import pytest

from api import webhooks_stripe
from api.canje import aplicar_compra
from api import compra_service, interpretation_service
from api.canje import SinDerecho
from api.models import Derecho, Interpretation, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db


def test_con_deuda_el_pago_salda_y_no_revienta(make_account, make_chart):
    cuenta = make_account()
    cuenta.deuda = 1
    cuenta.save(update_fields=["deuda"])
    carta = make_chart(account=cuenta)

    assert aplicar_compra(cuenta, "informe_natal", 2900, external_id="stripe:session:cs_d", chart=carta) is True

    cuenta.refresh_from_db()
    assert cuenta.deuda == 0
    assert Movimiento.objects.filter(external_id="stripe:session:cs_d").exists()
    assert not Movimiento.objects.filter(account=cuenta, tipo="consumo").exists()
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 0


def test_sin_deuda_sigue_canjeando(make_account, make_chart):
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    assert aplicar_compra(cuenta, "informe_natal", 2900, external_id="stripe:session:cs_ok", chart=carta) is True
    assert Movimiento.objects.filter(account=cuenta, tipo="consumo").exists()


def test_el_webhook_de_una_cuenta_con_deuda_responde_200_y_acredita(
    client, monkeypatch, settings, make_account, make_chart,
):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    cuenta = make_account()
    cuenta.deuda = 1
    cuenta.save(update_fields=["deuda"])
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_deuda", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    sesion = {
        "id": "cs_deuda", "payment_status": "paid", "amount_subtotal": 2900,
        "amount_total": 2900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_d", "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _id: sesion)
    cuerpo = json.dumps({
        "id": "evt_d", "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_deuda", "object": "checkout.session"}},
    }).encode()

    r = client.post(
        "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )

    assert r.status_code == 200
    fila.refresh_from_db()
    cuenta.refresh_from_db()
    assert fila.acreditado_at is not None
    assert cuenta.deuda == 0
    assert not Movimiento.objects.filter(account=cuenta, tipo="consumo").exists()
    assert not Interpretation.objects.filter(chart=fila.chart).exists()


def _fila(cuenta, make_chart):
    return PasarelaCheckout.objects.create(
        checkout_id="cs_x", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )


def test_sin_derecho_que_la_deuda_no_explica_sube(make_account, make_chart, monkeypatch):
    """Cobré y no entregué por una causa que no entendemos: tiene que subir
    (5xx y reintento), no quedar como un warning."""
    cuenta = make_account()
    fila = _fila(cuenta, make_chart)  # sin otorgamiento previo: la deuda no lo explica

    def sin_derecho(*a, **k):
        raise SinDerecho("leer_informe")

    monkeypatch.setattr(interpretation_service, "iniciar_generacion", sin_derecho)
    with pytest.raises(SinDerecho):
        compra_service.arrancar_informe(cuenta, fila)


def test_sin_derecho_tras_un_consumo_posterior_al_otorgamiento_sube(
    make_account, make_chart, monkeypatch,
):
    """El derecho se gastó en otra cosa después del pago: no es deuda."""
    cuenta = make_account()
    fila = _fila(cuenta, make_chart)
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="otorgamiento",
        cantidad=1, origen="compra", external_id="stripe:session:cs_x",
    )
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="consumo",
        cantidad=-1, origen="compra",
    )

    def sin_derecho(*a, **k):
        raise SinDerecho("leer_informe")

    monkeypatch.setattr(interpretation_service, "iniciar_generacion", sin_derecho)
    with pytest.raises(SinDerecho):
        compra_service.arrancar_informe(cuenta, fila)


def test_un_consumo_de_otro_producto_no_esconde_la_deuda(make_account, make_chart, monkeypatch):
    """Revisión final, Important 3: una `lectura_breve` gastada en otra carta
    entre el otorgamiento y el arranque no es el informe comprado. El rastro
    se mira por producto; si no, un caso legítimo de deuda subía como 5xx y
    Stripe reintentaba tres días."""
    cuenta = make_account()
    fila = _fila(cuenta, make_chart)
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="otorgamiento",
        cantidad=1, origen="compra", external_id="stripe:session:cs_x",
    )
    Movimiento.objects.create(
        account=cuenta, codigo_producto="lectura_breve", tipo="consumo",
        cantidad=-1, origen="compra",
    )

    def sin_derecho(*a, **k):
        raise SinDerecho("leer_informe")

    monkeypatch.setattr(interpretation_service, "iniciar_generacion", sin_derecho)
    compra_service.arrancar_informe(cuenta, fila)  # no sube

    fila.refresh_from_db()
    assert fila.saldo_deuda is True
