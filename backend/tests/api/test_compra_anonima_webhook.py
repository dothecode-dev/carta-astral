"""El webhook adjudica la compra anónima por el mail del pago (RF5, RF7, RF9).

Superficie crítica: plata + identidad. La regla que sostiene todo lo demás es
que `cuenta_nueva` sólo es True cuando ESTA compra creó la cuenta: es lo que
después (RF11) decide si el navegador que pagó puede entrar. Pagar con el
mail de otra persona acredita en su cuenta, pero nunca la marca como nueva.

Y sólo se confía en mails PROBADOS (identidad email o cuenta verificada): una
cuenta con el mail sin verificar puede ser de alguien que lo tomó prestado
(pre-account-hijacking) y nunca recibe la compra ni la identidad.
"""

import logging

import pytest
from django.conf import settings as django_settings

from api import analitica, codigos_acceso
from api.identity import sub_hash
from api.models import (
    Account, Chart, Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout, ProviderIdentity,
    SubTombstone, Sujeto,
)
from tests.api.conftest import PI_ANONIMA, SESSION_ANONIMA, con_mail, sesion_anonima

pytestmark = pytest.mark.django_db


def _entrar_por_codigo(client, email):
    """El login por código de hoy (`test_codigo_endpoints`): la cuenta en la
    que cae quien prueba que el mail es suyo."""
    _, claro, _ = codigos_acceso.pedir(email)
    r = client.post("/api/auth/email", {"email": email, "codigo": claro},
                    content_type="application/json")
    assert r.status_code == 200
    return str(r.json()["account_id"])


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
    assert Chart.objects.get(pk=anonima.sujeto.natal_de_id).account == cuenta
    assert Sujeto.objects.get(natal_de_id=anonima.sujeto.natal_de_id).account == cuenta
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


def test_cuenta_verificada_sin_identidad_recibe_la_compra_y_la_identidad(
    client, entregar_anonima, anonima, make_account, sin_hilo,
):
    dueña = make_account(email="ya@mail.com", email_verified=True)

    assert entregar_anonima(con_mail("YA@mail.com")).status_code == 200

    anonima.refresh_from_db()
    assert anonima.account == dueña and anonima.cuenta_nueva is False
    assert Account.objects.filter(email__iexact="ya@mail.com").count() == 1
    assert Chart.objects.get(pk=anonima.sujeto.natal_de_id).account == dueña
    assert ProviderIdentity.objects.filter(provider="email", sub="ya@mail.com", account=dueña).exists()
    # Sin regalo nuevo: la cuenta ya existía.
    assert _restante(dueña, "lectura_breve") == 0
    assert _entrar_por_codigo(client, "ya@mail.com") == str(dueña.pk)


def test_una_cuenta_con_el_mail_sin_verificar_no_recibe_nada(
    client, entregar_anonima, anonima, make_account, sin_hilo,
):
    """Pre-account-hijacking: alguien entra con Google usando un mail ajeno que
    Google no verificó (`sso.py` lo acepta) y queda una cuenta con ese mail sin
    verificar. La compra de la dueña real del mail no puede ir a parar ahí:
    se crea OTRA cuenta, y es en ésa donde la dueña entra por código."""
    atacante = make_account(email="victima@mail.com", email_verified=False)
    ProviderIdentity.objects.create(provider="google", sub="g-atacante", account=atacante)

    entregar_anonima(con_mail("Victima@mail.com"))

    anonima.refresh_from_db()
    nueva = anonima.account
    assert nueva is not None and nueva != atacante and anonima.cuenta_nueva is True
    assert Chart.objects.get(pk=anonima.sujeto.natal_de_id).account == nueva
    assert Sujeto.objects.get(natal_de_id=anonima.sujeto.natal_de_id).account == nueva
    assert not Movimiento.objects.filter(account=atacante).exists()
    assert not ProviderIdentity.objects.filter(account=atacante, provider="email").exists()
    assert ProviderIdentity.objects.get(provider="email", sub="victima@mail.com").account == nueva
    assert _entrar_por_codigo(client, "victima@mail.com") == str(nueva.pk)


def test_con_varias_cuentas_verificadas_del_mismo_mail_va_a_la_mas_antigua(
    entregar_anonima, anonima, make_account, sin_hilo,
):
    vieja = make_account(email="Dup@mail.com", email_verified=True)
    make_account(email="dup@mail.com", email_verified=True)

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


def test_la_identidad_email_manda_sobre_una_cuenta_verificada_mas_antigua(
    entregar_anonima, anonima, make_account, sin_hilo,
):
    """La identidad `(email, mail)` es la puerta por la que entra quien prueba
    el mail: si existe, la compra va ahí aunque otra cuenta verificada más
    antigua tenga el mismo mail en `Account.email`."""
    make_account(email="puerta@mail.com", email_verified=True)
    con_puerta = make_account(email="puerta@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="puerta@mail.com", account=con_puerta)

    entregar_anonima(con_mail("puerta@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == con_puerta and anonima.cuenta_nueva is False


def test_cuenta_verificada_con_identidad_no_la_duplica(entregar_anonima, anonima, make_account, sin_hilo):
    dueña = make_account(email="conid@mail.com", email_verified=True)
    ProviderIdentity.objects.create(provider="email", sub="conid@mail.com", account=dueña)

    entregar_anonima(con_mail("conid@mail.com"))

    anonima.refresh_from_db()
    assert anonima.account == dueña and anonima.cuenta_nueva is False
    assert ProviderIdentity.objects.filter(provider="email", sub="conid@mail.com").count() == 1


def test_la_carta_se_adjudica_por_el_sujeto_del_checkout(entregar_anonima, anonima, sin_hilo):
    """CONTRAER: adjudicar busca la carta por `fila.sujeto`, no por `fila.chart`."""
    carta_id = anonima.sujeto.natal_de_id

    assert entregar_anonima(con_mail("otra@mail.com")).status_code == 200

    anonima.refresh_from_db()
    assert Chart.objects.get(pk=carta_id).account == anonima.account
    assert Sujeto.objects.get(natal_de_id=carta_id).account == anonima.account
    assert _restante(anonima.account, "informe_natal") == 0
    assert len(sin_hilo) == 1
