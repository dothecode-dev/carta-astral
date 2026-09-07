"""`acreditar_sesion`: el «procedimiento manual» de cuando el webhook no
acredita porque algo no cerró contra la fila congelada.

Antes de esto, resolución manual era `grant_credits`: sin constancia del
cupón, sin `acreditado_at`, sin informe arrancado.
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api import webhooks_stripe
from api.models import Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout

pytestmark = pytest.mark.django_db

SESSION = "cs_manual"


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda sid: {
        "id": SESSION, "payment_status": "paid", "amount_subtotal": 2900, "amount_total": 2320,
        "total_details": {"amount_discount": 580}, "discounts": [{"promotion_code": "promo_1"}],
        "payment_intent": "pi_manual", "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    })
    monkeypatch.setattr(webhooks_stripe, "arrancar_informe", lambda cuenta, fila: None)


@pytest.fixture
def compra(make_account):
    cupon = Cupon.objects.create(codigo="MANUAL", porcentaje=30, productos=["informe_natal"], usos_maximos=5,
                                 stripe_promotion_code_id="promo_1")
    return PasarelaCheckout.objects.create(checkout_id=SESSION, account=make_account(),
                                           codigo_producto="informe_natal", cupon=cupon, descuento_centavos=870)


def _restante(cuenta):
    d = Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").first()
    return d.cantidad_restante if d else 0


def test_sin_el_flag_muestra_y_no_acredita(compra, capsys):
    call_command("acreditar_sesion", SESSION)

    salida = capsys.readouterr().out
    assert "870" in salida and "580" in salida and "MANUAL" in salida
    assert _restante(compra.account) == 0


def test_con_el_flag_acredita_con_el_descuento_congelado_y_deja_constancia(compra, capsys):
    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert _restante(compra.account) == 1
    compra.refresh_from_db()
    assert compra.acreditado_at is not None and compra.payment_intent == "pi_manual"
    uso = CuponUso.objects.get(cupon=compra.cupon)
    assert (uso.descuento_centavos, uso.monto_pagado_centavos, uso.external_id) == (870, 2030, f"stripe:session:{SESSION}")
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").exists()


def test_correrlo_dos_veces_no_otorga_dos(compra):
    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")
    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert _restante(compra.account) == 1 and CuponUso.objects.count() == 1


def test_una_sesion_que_no_registramos_no_se_acredita():
    with pytest.raises(CommandError):
        call_command("acreditar_sesion", "cs_desconocida", "--si-estoy-seguro")
