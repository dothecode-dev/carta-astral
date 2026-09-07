"""Acreditar una compra con cupón: el webhook valida contra la fila congelada.

Tres cosas tienen que cerrar antes de otorgar: que `amount_subtotal` sea el
precio de lista, que la sesión traiga exactamente NUESTRO promotion code, y que
`total_details.amount_discount` sea el descuento que congelamos al abrir. La
excepción, medida en sandbox el 06-09-2026: si el cupón se agotó entre abrir y
pagar, Stripe le quita el descuento y cobra la lista — eso se acredita.
"""
import json
import logging

import pytest
from django.db import IntegrityError

from api import analitica, webhooks_stripe
from api.models import Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
SESSION = "cs_test_cupon"


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    monkeypatch.setattr(webhooks_stripe, "arrancar_informe", lambda cuenta, fila: None)


@pytest.fixture
def eventos(monkeypatch):
    lista = []
    monkeypatch.setattr(analitica, "evento", lambda acc, nombre, props: lista.append((nombre, props)))
    return lista


def _sesion(**cambios) -> dict:
    """Una sesión pagada con el 30 % sobre informe_natal, como la devolvió el
    sandbox el 06-09-2026."""
    sesion = {
        "id": SESSION, "payment_status": "paid",
        "amount_subtotal": 2900, "amount_total": 2030,
        "total_details": {"amount_tax": 0, "amount_discount": 870, "amount_shipping": 0},
        "discounts": [{"coupon": None, "promotion_code": "promo_1"}],
        "payment_intent": "pi_cupon", "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    }
    sesion.update(cambios)
    return sesion


def _entregar(client, monkeypatch, sesion, tipo="checkout.session.completed", evt="evt_1"):
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda session_id: sesion)
    cuerpo = json.dumps({"id": evt, "type": tipo, "data": {"object": {"id": SESSION}}}).encode()
    return client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))


@pytest.fixture
def promo():
    return Cupon.objects.create(codigo="PROMO30", porcentaje=30, productos=["informe_natal", "pack_5_natal"],
                                usos_maximos=10, stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1")


@pytest.fixture
def compra(make_account, promo):
    return PasarelaCheckout.objects.create(checkout_id=SESSION, account=make_account(),
                                           codigo_producto="informe_natal", cupon=promo, descuento_centavos=870)


def _restante(cuenta):
    d = Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").first()
    return d.cantidad_restante if d else 0


def test_una_compra_con_descuento_acredita_el_producto_entero_y_registra_el_uso(client, monkeypatch, compra, eventos):
    r = _entregar(client, monkeypatch, _sesion())

    assert r.status_code == 200
    assert _restante(compra.account) == 1
    uso = CuponUso.objects.get(cupon=compra.cupon)
    assert (uso.account, uso.codigo_producto, uso.descuento_centavos, uso.monto_pagado_centavos) == (
        compra.account, "informe_natal", 870, 2030,
    )
    assert uso.external_id == f"stripe:session:{SESSION}" and uso.checkout == compra
    (nombre, props), = eventos
    assert nombre == "compra_completada" and props["monto_centavos"] == 2030 and props["cupon"] == "PROMO30"


def test_el_reintento_de_stripe_no_cuenta_dos_usos(client, monkeypatch, compra, eventos):
    _entregar(client, monkeypatch, _sesion())
    _entregar(client, monkeypatch, _sesion(), evt="evt_2")

    assert _restante(compra.account) == 1
    assert CuponUso.objects.count() == 1
    assert len(eventos) == 1


def test_completed_y_async_payment_succeeded_de_la_misma_sesion_cuentan_un_uso(client, monkeypatch, compra):
    _entregar(client, monkeypatch, _sesion(), tipo="checkout.session.completed")
    _entregar(client, monkeypatch, _sesion(), tipo="checkout.session.async_payment_succeeded", evt="evt_2")

    assert CuponUso.objects.count() == 1


def test_si_stripe_dice_otro_descuento_que_el_congelado_no_acredita(client, monkeypatch, compra, caplog):
    with caplog.at_level(logging.ERROR):
        r = _entregar(client, monkeypatch, _sesion(amount_total=2320, total_details={"amount_discount": 580}))

    assert r.status_code == 200  # definitivo: reintentar no lo arregla
    assert _restante(compra.account) == 0 and CuponUso.objects.count() == 0
    assert any("870" in m and "580" in m for m in caplog.messages)


def test_un_subtotal_distinto_al_catalogo_no_acredita_aunque_haya_descuento(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, _sesion(amount_subtotal=2030, amount_total=1160))

    assert r.status_code == 200
    assert _restante(compra.account) == 0 and CuponUso.objects.count() == 0


def test_un_promotion_code_que_no_es_el_nuestro_no_acredita(client, monkeypatch, compra):
    r = _entregar(client, monkeypatch, _sesion(discounts=[{"coupon": None, "promotion_code": "promo_ajeno"}]))

    assert r.status_code == 200
    assert _restante(compra.account) == 0 and CuponUso.objects.count() == 0


def test_una_compra_sin_cupon_que_llega_con_descuento_no_acredita(client, monkeypatch, make_account):
    """La puerta de A1: un descuento que nuestra base no conoce."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal")

    r = _entregar(client, monkeypatch, _sesion())

    assert r.status_code == 200
    assert _restante(cuenta) == 0


def test_si_el_cupon_se_agoto_entre_abrir_y_pagar_se_acredita_a_precio_de_lista(client, monkeypatch, compra, eventos, caplog):
    """Medido: Stripe quita el descuento y cobra la lista. La persona pagó
    29, recibe su informe, y el cupón no cuenta un uso."""
    with caplog.at_level(logging.WARNING):
        r = _entregar(client, monkeypatch, _sesion(amount_total=2900, total_details={"amount_discount": 0}, discounts=[]))

    assert r.status_code == 200
    assert _restante(compra.account) == 1
    assert CuponUso.objects.count() == 0
    compra.refresh_from_db()
    assert compra.descuento_centavos == 0
    assert eventos[0][1]["monto_centavos"] == 2900 and eventos[0][1]["cupon"] is None
    assert any("PROMO30" in m and "removido" in m for m in caplog.messages)


def test_el_uso_se_registra_aunque_el_cupon_ya_este_desactivado(client, monkeypatch, compra):
    compra.cupon.activo = False
    compra.cupon.save()

    _entregar(client, monkeypatch, _sesion())

    assert _restante(compra.account) == 1 and CuponUso.objects.count() == 1


def test_un_fallo_al_registrar_el_uso_no_revierte_la_compra(client, monkeypatch, compra, caplog):
    def explota(**kw):
        raise IntegrityError("simulado")

    monkeypatch.setattr(webhooks_stripe.CuponUso.objects, "get_or_create", explota)

    with caplog.at_level(logging.ERROR):
        r = _entregar(client, monkeypatch, _sesion())

    assert r.status_code == 200
    assert _restante(compra.account) == 1
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").exists()
    assert any("uso" in m.lower() and "PROMO30" in m for m in caplog.messages)
