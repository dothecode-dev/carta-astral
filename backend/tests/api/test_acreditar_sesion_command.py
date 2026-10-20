"""`acreditar_sesion`: el «procedimiento manual» de cuando el webhook no
acredita porque algo no cerró contra la fila congelada.

Antes de esto, resolución manual era `grant_credits`: sin constancia del
cupón, sin `acreditado_at`, sin informe arrancado.
"""
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from api import cobro, webhooks_stripe
from api.models import Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout

pytestmark = pytest.mark.django_db

SESSION = "cs_manual"


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda sid: {
        "id": SESSION, "payment_status": "paid", "currency": "usd", "amount_subtotal": 2900, "amount_total": 2320,
        "total_details": {"amount_discount": 580}, "discounts": [{"promotion_code": "promo_1"}],
        "payment_intent": "pi_manual", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    })
    monkeypatch.setattr(cobro, "arrancar_informe", lambda cuenta, fila: None)


@pytest.fixture
def compra(make_account):
    cupon = Cupon.objects.create(codigo="MANUAL", porcentaje=30, productos=["informe_natal"], usos_maximos=5,
                                 stripe_promotion_code_id="promo_1")
    return PasarelaCheckout.objects.create(pasarela=PasarelaCheckout.STRIPE, checkout_id=SESSION, account=make_account(),
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
    assert compra.acreditado_at is not None and compra.pago_id == "pi_manual"
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


def test_muestra_la_moneda_de_los_dos_lados(compra, capsys):
    """Un 2900 contra un 2900 no dicen nada si uno es `brl` y el otro `usd`."""
    compra.moneda = "brl"
    compra.precio_centavos = 14900
    compra.save(update_fields=["moneda", "precio_centavos"])

    call_command("acreditar_sesion", SESSION)

    salida = capsys.readouterr().out
    assert "14900 brl" in salida
    assert "2900 usd" in salida


def test_una_fila_disputada_no_se_acredita_sin_el_segundo_flag(compra, capsys):
    compra.disputa_id = "du_manual"
    compra.save(update_fields=["disputa_id"])

    with pytest.raises(CommandError):
        call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert "DISPUTADA" in capsys.readouterr().out
    assert _restante(compra.account) == 0
    compra.refresh_from_db()
    assert compra.acreditado_at is None


def test_una_fila_disputada_se_acredita_con_los_dos_flags(compra):
    compra.disputa_id = "du_manual"
    compra.save(update_fields=["disputa_id"])

    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro", "--aunque-disputada")

    assert _restante(compra.account) == 1


def test_una_compra_sin_cuenta_que_el_webhook_rechazo_se_acredita_a_mano(
    anonima, entregar_anonima, sin_hilo, settings,
):
    """Fase 2: la cuenta de una compra sin cuenta la pone `cobro`, DESPUÉS de
    las validaciones de Stripe. Si una falla, la fila queda sin cuenta pero con
    el mail del pago, y el procedimiento manual tiene que poder resolverla
    (antes, el webhook adjudicaba antes de validar)."""
    from tests.api.conftest import SESSION_ANONIMA, con_mail

    settings.STRIPE_PRODUCTOS = {"pack_5_natal": "prod_natal"}  # el Product no cierra contra la fila
    assert entregar_anonima(con_mail("manual@mail.com")).status_code == 200
    anonima.refresh_from_db()
    assert anonima.account is None and anonima.mail_comprador == "manual@mail.com"
    PasarelaCheckout.objects.filter(pk=anonima.pk).update(descuento_centavos=0, cupon=None)

    call_command("acreditar_sesion", SESSION_ANONIMA, "--si-estoy-seguro")

    anonima.refresh_from_db()
    assert anonima.account is not None and anonima.account.email == "manual@mail.com"
    assert anonima.acreditado_at is not None
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}").count() == 1


def test_si_el_cobro_la_rechaza_es_un_error_y_no_dice_acreditada(compra, monkeypatch, capsys):
    """`cobro.acreditar` devuelve False sin acreditar (acá, un pago sin id):
    el comando no puede decir «acreditada»."""
    monkeypatch.setattr(cobro, "avisar", lambda texto: None)
    sesion = webhooks_stripe.obtener_sesion(SESSION)
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda sid: {**sesion, "payment_intent": None})

    with pytest.raises(CommandError, match="no se acreditó"):
        call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert "acreditada" not in capsys.readouterr().out
    assert _restante(compra.account) == 0


def test_una_sesion_ya_acreditada_dice_que_ya_estaba(compra, capsys):
    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")
    capsys.readouterr()

    call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    salida = capsys.readouterr().out
    assert "ya estaba acreditada" in salida and "pi_manual" in salida
    assert _restante(compra.account) == 1


def test_un_pago_duplicado_es_un_error_claro(compra):
    """La fila ya la acreditó otro pago: no se otorga y no sale un traceback."""
    compra.acreditado_at = timezone.now()
    compra.pago_id = "pi_otro"
    compra.save(update_fields=["acreditado_at", "pago_id"])

    with pytest.raises(CommandError, match="pi_otro.*duplicado"):
        call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert _restante(compra.account) == 0


def test_una_disputa_que_entra_despues_del_chequeo_frena_igual(compra, monkeypatch):
    """El comando mira la disputa sobre la fila que leyó al principio; si entra
    mientras tanto, la tiene que frenar `cobro` bajo el lock."""
    sesion = webhooks_stripe.obtener_sesion(SESSION)

    def disputa_mientras_tanto(sid):
        PasarelaCheckout.objects.filter(pk=compra.pk).update(disputa_id="du_tarde")
        return sesion

    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", disputa_mientras_tanto)

    with pytest.raises(CommandError, match="disputa"):
        call_command("acreditar_sesion", SESSION, "--si-estoy-seguro")

    assert _restante(compra.account) == 0


def test_una_compra_sin_cuenta_cuyo_webhook_nunca_llego_toma_el_mail_de_la_sesion(anonima, sin_hilo, monkeypatch):
    """Sin ninguna entrega del webhook la fila no tiene `mail_comprador`: el
    comando lo toma del pago, que es de donde lo toma el webhook."""
    from tests.api.conftest import PRECIO_ANONIMA, SESSION_ANONIMA, con_mail

    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda sid: con_mail("tarde@mail.com"))
    from django.conf import settings
    monkeypatch.setattr(settings, "STRIPE_PRODUCTOS", {"informe_natal": PRECIO_ANONIMA})
    assert anonima.mail_comprador == ""

    call_command("acreditar_sesion", SESSION_ANONIMA, "--si-estoy-seguro")

    anonima.refresh_from_db()
    assert anonima.account is not None and anonima.account.email == "tarde@mail.com"
    assert anonima.acreditado_at is not None
