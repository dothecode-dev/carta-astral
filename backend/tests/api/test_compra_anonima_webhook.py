"""El webhook adjudica la compra anónima por el mail del pago (RF5, RF7, RF9).

Superficie crítica: plata + identidad. La regla que sostiene todo lo demás es
que `cuenta_nueva` sólo es True cuando ESTA compra creó la cuenta: es lo que
después (RF11) decide si el navegador que pagó puede entrar. Pagar con el
mail de otra persona acredita en su cuenta, pero nunca la marca como nueva.
"""

import logging

import pytest
from django.conf import settings as django_settings

from api import analitica
from api.identity import sub_hash
from api.models import (
    Account, Chart, Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout, ProviderIdentity,
    SubTombstone, Sujeto,
)
from tests.api.conftest import PI_ANONIMA, SESSION_ANONIMA, con_mail, sesion_anonima

pytestmark = pytest.mark.django_db


def _restante(cuenta, codigo):
    d = Derecho.objects.filter(account=cuenta, codigo_producto=codigo).first()
    return d.cantidad_restante if d else 0


def test_mail_nuevo_crea_cuenta_sin_verificar_y_le_pasa_la_carta(entregar_anonima, anonima, sin_hilo):
    assert entregar_anonima(con_mail("  Nueva@Mail.com ")).status_code == 200

    anonima.refresh_from_db()
    cuenta = anonima.account
    assert cuenta is not None
    assert cuenta.email == "nueva@mail.com" and cuenta.email_verified is False
    assert anonima.cuenta_nueva is True and anonima.acreditado_at is not None
    assert ProviderIdentity.objects.filter(provider="email", sub="nueva@mail.com", account=cuenta).exists()
    assert Chart.objects.get(pk=anonima.chart_id).account == cuenta
    assert Sujeto.objects.get(natal_de_id=anonima.chart_id).account == cuenta
    # El informe comprado quedó canjeado contra la carta y escribiéndose.
    assert _restante(cuenta, "informe_natal") == 0
    assert len(sin_hilo) == 1


def test_la_cuenta_creada_recibe_el_regalo_de_bienvenida_como_cualquier_alta(
    entregar_anonima, anonima, sin_hilo,
):
    """Mismo camino que el alta por mail de hoy (`resolve_account`): la
    lectura breve de regalo, una vez."""
    entregar_anonima(con_mail("regalo@mail.com"))

    anonima.refresh_from_db()
    cuenta = anonima.account
    assert _restante(cuenta, "lectura_breve") == django_settings.INSTALL_FREE_CREDITS
    assert Movimiento.objects.filter(account=cuenta, external_id=f"bienvenida:{cuenta.pk}").count() == 1


def test_el_tombstone_descuenta_el_regalo_de_una_cuenta_borrada(entregar_anonima, anonima, sin_hilo):
    SubTombstone.objects.create(
        sub_hash=sub_hash("email", "volvio@mail.com"),
        free_credits_consumed=django_settings.INSTALL_FREE_CREDITS,
    )
    entregar_anonima(con_mail("volvio@mail.com"))

    anonima.refresh_from_db()
    assert anonima.cuenta_nueva is True
    assert _restante(anonima.account, "lectura_breve") == 0
    assert not Movimiento.objects.filter(external_id=f"bienvenida:{anonima.account.pk}").exists()


def test_mail_existente_acredita_ahi_sin_cuenta_nueva(entregar_anonima, anonima, make_account, sin_hilo):
    dueña = make_account(email="ya@mail.com", email_verified=True)

    assert entregar_anonima(con_mail("YA@mail.com")).status_code == 200

    anonima.refresh_from_db()
    assert anonima.account == dueña and anonima.cuenta_nueva is False
    assert Account.objects.filter(email__iexact="ya@mail.com").count() == 1
    assert Chart.objects.get(pk=anonima.chart_id).account == dueña
    # Sin regalo nuevo: la cuenta ya existía.
    assert _restante(dueña, "lectura_breve") == 0


def test_mail_existente_sin_verificar_tambien_es_esa(entregar_anonima, anonima, make_account, sin_hilo):
    previa = make_account(email="previa@mail.com", email_verified=False)

    entregar_anonima(con_mail("previa@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == previa and anonima.cuenta_nueva is False


def test_con_varias_cuentas_del_mismo_mail_va_a_la_mas_antigua(
    entregar_anonima, anonima, make_account, sin_hilo,
):
    vieja = make_account(email="Dup@mail.com")
    make_account(email="dup@mail.com")

    entregar_anonima(con_mail("dup@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == vieja and anonima.cuenta_nueva is False


def test_una_identidad_email_previa_de_otra_cuenta_no_es_cuenta_nueva(
    entregar_anonima, anonima, make_account, sin_hilo,
):
    """El `iexact` sobre `Account.email` no la ve (la cuenta tiene otro mail),
    pero `resolve_account` la encuentra por `ProviderIdentity(email, sub)`. Es
    una cuenta que existía antes de la compra: jamás `cuenta_nueva`."""
    otra = make_account(email="otro@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="alias@mail.com", account=otra)

    entregar_anonima(con_mail("alias@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == otra and anonima.cuenta_nueva is False
    assert Account.objects.count() == 1


def test_la_segunda_entrega_no_crea_otra_cuenta_ni_acredita_dos_veces(
    entregar_anonima, anonima, sin_hilo,
):
    entregar_anonima(con_mail("dos@mail.com"))
    entregar_anonima(con_mail("dos@mail.com"), tipo="checkout.session.async_payment_succeeded", evt="evt_2")

    anonima.refresh_from_db()
    assert Account.objects.filter(email="dos@mail.com").count() == 1
    assert anonima.cuenta_nueva is True
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}").count() == 1


def test_sin_mail_pide_reintento(entregar_anonima, anonima, caplog):
    with caplog.at_level(logging.ERROR):
        r = entregar_anonima(sesion_anonima(customer_details={}))

    assert r.status_code == 500
    anonima.refresh_from_db()
    assert anonima.account is None and anonima.acreditado_at is None
    assert Account.objects.count() == 0
    assert any(rec.levelno >= logging.ERROR for rec in caplog.records)


@pytest.mark.parametrize("detalles", [None, {"email": None}, {"email": "   "}])
def test_mail_ausente_en_cualquier_forma_pide_reintento(entregar_anonima, anonima, detalles):
    assert entregar_anonima(sesion_anonima(customer_details=detalles)).status_code == 500
    anonima.refresh_from_db()
    assert anonima.account is None and Account.objects.count() == 0


def test_una_sesion_sin_pagar_no_crea_cuenta(entregar_anonima, anonima):
    r = entregar_anonima(con_mail("espera@mail.com", payment_status="unpaid"))

    assert r.status_code == 200
    anonima.refresh_from_db()
    assert anonima.account is None and Account.objects.count() == 0


def test_el_log_no_lleva_el_mail_completo(entregar_anonima, anonima, sin_hilo, caplog):
    with caplog.at_level(logging.DEBUG):
        entregar_anonima(con_mail("secreto.total@mail.com"))

    assert anonima.__class__.objects.get(pk=anonima.pk).account is not None
    assert "secreto.total@mail.com" not in caplog.text


def test_el_uso_del_cupon_queda_en_la_cuenta_adjudicada(entregar_anonima, anonima, sin_hilo):
    promo = Cupon.objects.create(
        codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=10,
        stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1",
    )
    PasarelaCheckout.objects.filter(pk=anonima.pk).update(cupon=promo, descuento_centavos=870)

    r = entregar_anonima(con_mail(
        "cupon@mail.com", amount_total=2030,
        total_details={"amount_tax": 0, "amount_discount": 870},
        discounts=[{"coupon": None, "promotion_code": "promo_1"}],
    ))

    assert r.status_code == 200
    anonima.refresh_from_db()
    uso = CuponUso.objects.get(cupon=promo)
    assert uso.account == anonima.account and uso.account is not None
    assert uso.monto_pagado_centavos == 2030


def test_la_telemetria_sale_con_la_cuenta_adjudicada(entregar_anonima, anonima, sin_hilo, monkeypatch):
    eventos = []
    monkeypatch.setattr(analitica, "evento", lambda acc, nombre, props: eventos.append((acc, nombre)))

    entregar_anonima(con_mail("medida@mail.com"))

    anonima.refresh_from_db()
    assert eventos == [(anonima.account, "compra_completada")]


def test_reembolso_de_una_compra_anonima(client, entregar_anonima, anonima, sin_hilo):
    """RF9: el reembolso busca la fila por `payment_intent` y revoca en la
    cuenta que adjudicó el pago. Mismo evento que `test_stripe_webhook_refund`."""
    import json

    from tests.api.stripe_firma import firmar

    entregar_anonima(con_mail("r@mail.com"))
    anonima.refresh_from_db()
    assert anonima.payment_intent == PI_ANONIMA

    refund = {
        "id": "re_anonima", "object": "refund", "amount": 2900, "currency": "usd",
        "charge": "ch_1", "payment_intent": PI_ANONIMA, "reason": None, "status": "succeeded",
    }
    cuerpo = json.dumps({"id": "evt_r", "type": "refund.created", "data": {"object": refund}}).encode()
    r = client.post(
        "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )

    assert r.status_code == 200
    revocacion = Movimiento.objects.get(tipo="revocacion", external_id="stripe:refund:re_anonima")
    assert revocacion.account == anonima.account


# --- Fix round 1 -------------------------------------------------------------


def test_si_falla_despues_de_adjudicar_el_reintento_acredita_en_la_misma_cuenta(
    entregar_anonima, anonima, sin_hilo, monkeypatch,
):
    """`adjudicar` commitea en su propia transacción: un fallo al acreditar deja
    la fila con cuenta y sin Movimiento. El reintento de Stripe tiene que
    acreditar ahí, sin crear otra cuenta ni perder `cuenta_nueva`."""
    from api import webhooks_stripe

    real = webhooks_stripe.aplicar_compra
    llamadas = []

    def falla_la_primera(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("la base se cayó")
        return real(*args, **kwargs)

    monkeypatch.setattr(webhooks_stripe, "aplicar_compra", falla_la_primera)

    assert entregar_anonima(con_mail("reintento@mail.com")).status_code == 500
    anonima.refresh_from_db()
    cuenta = anonima.account
    assert cuenta is not None and anonima.cuenta_nueva is True
    assert not Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}").exists()

    assert entregar_anonima(con_mail("reintento@mail.com"), evt="evt_2").status_code == 200
    anonima.refresh_from_db()
    assert anonima.account == cuenta and anonima.cuenta_nueva is True
    movs = Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}")
    assert movs.count() == 1 and movs.get().account == cuenta
    assert Account.objects.filter(email="reintento@mail.com").count() == 1


def test_cuenta_existente_sin_verificar_queda_alcanzable_por_el_login_con_codigo(
    client, entregar_anonima, anonima, make_account, sin_hilo,
):
    """Una cuenta sin verificar y sin identidad email: `resolve_account` sólo
    enlaza cuentas VERIFICADAS por mail, así que sin la identidad el login por
    código crearía otra cuenta y la compra quedaría invisible para quien
    pagó (RF12/RF17). La adjudicación le agrega la identidad, sin verificarla
    ni marcarla nueva."""
    from api import codigos_acceso

    previa = make_account(email="Sinverif@mail.com", email_verified=False)

    entregar_anonima(con_mail("sinverif@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == previa and anonima.cuenta_nueva is False
    previa.refresh_from_db()
    assert previa.email_verified is False
    assert ProviderIdentity.objects.filter(provider="email", sub="sinverif@mail.com", account=previa).exists()

    _, claro, _ = codigos_acceso.pedir("sinverif@mail.com")
    r = client.post("/api/auth/email", {"email": "sinverif@mail.com", "codigo": claro},
                    content_type="application/json")
    assert r.status_code == 200
    assert str(r.json()["account_id"]) == str(previa.pk)
    assert Account.objects.filter(email__iexact="sinverif@mail.com").count() == 1


def test_cuenta_verificada_con_identidad_no_la_duplica(entregar_anonima, anonima, make_account, sin_hilo):
    dueña = make_account(email="conid@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="conid@mail.com", account=dueña)

    entregar_anonima(con_mail("conid@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == dueña and anonima.cuenta_nueva is False
    assert ProviderIdentity.objects.filter(provider="email", sub="conid@mail.com").count() == 1


def test_si_la_identidad_email_es_de_otra_cuenta_no_se_toca(
    entregar_anonima, anonima, make_account, sin_hilo, caplog,
):
    """El mail matchea una cuenta por `Account.email`, pero la identidad
    `(email, mail)` ya es de OTRA cuenta: no se mueve nada, se avisa."""
    por_mail = make_account(email="choque@mail.com", email_verified=False)
    otra = make_account(email="otra@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="choque@mail.com", account=otra)

    with caplog.at_level(logging.WARNING):
        entregar_anonima(con_mail("choque@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == por_mail and anonima.cuenta_nueva is False
    assert ProviderIdentity.objects.get(provider="email", sub="choque@mail.com").account == otra
    assert any(r.levelno == logging.WARNING for r in caplog.records)
    assert "choque@mail.com" not in caplog.text
