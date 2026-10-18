"""Disputas (RF15, EC11, EC16, Review Focus 4). Payload MEDIDO el 13-10-2026:
`charge.dispute.funds_withdrawn` trae `id`, `charge`, `payment_intent`,
`amount`, `currency`, `reason`, y puede llegar ANTES que `completed`."""

import json

import pytest

from api import disputas, stripe_client, webhooks_stripe
from api.models import Derecho, MailBloqueado, Movimiento, PasarelaCheckout
from api.sujetos import sujeto_natal
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}


@pytest.fixture
def avisos_enviados(monkeypatch):
    enviados = []
    monkeypatch.setattr(webhooks_stripe, "avisar_admin", enviados.append)
    monkeypatch.setattr(disputas, "avisar_admin", enviados.append)
    return enviados


def _disputa(client, tipo="charge.dispute.funds_withdrawn", **cambios):
    dispute = {
        "id": "du_1", "object": "dispute", "charge": "ch_1", "payment_intent": "pi_1",
        "amount": 14900, "currency": "brl", "reason": "fraudulent", "status": "needs_response",
    }
    dispute.update(cambios)
    cuerpo = json.dumps({"id": "evt_du", "type": tipo, "data": {"object": dispute}}).encode()
    return client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))


@pytest.fixture
def compra_acreditada(make_account, make_chart, sin_hilo):
    """Una compra `brl` ya entregada, con su derecho sin canjear."""
    from django.utils import timezone

    from api.canje import aplicar_compra

    cuenta = make_account(email="ana@mail.com")
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_du", account=cuenta, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900, payment_intent="pi_1", acreditado_at=timezone.now(),
    )
    aplicar_compra(cuenta, "informe_natal", 14900, external_id="stripe:session:cs_du", precio_centavos=14900)
    return fila


def _restante(cuenta):
    d = Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").first()
    return d.cantidad_restante if d else 0


def test_funds_withdrawn_revoca_anota_bloquea_y_avisa(client, compra_acreditada, avisos_enviados):
    r = _disputa(client)

    assert r.status_code == 200
    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id == "du_1"
    assert compra_acreditada.reembolsado_centavos == 14900
    assert _restante(compra_acreditada.account) == 0
    assert MailBloqueado.bloqueado("ana@mail.com")
    # El mail va enmascarado: el aviso sale a Telegram y, sin token, al log.
    assert any("du_1" in a and "cs_du" in a and "brl" in a and "a***@mail.com" in a for a in avisos_enviados)
    assert not any("ana@mail.com" in a for a in avisos_enviados)


def test_la_misma_disputa_dos_veces_es_un_no_op(client, compra_acreditada, avisos_enviados):
    _disputa(client)
    _disputa(client)

    compra_acreditada.refresh_from_db()
    assert compra_acreditada.reembolsado_centavos == 14900
    assert len(avisos_enviados) == 1


def test_funds_reinstated_devuelve_lo_revocado_y_desbloquea(client, compra_acreditada, avisos_enviados):
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert _restante(compra_acreditada.account) == 1
    assert not MailBloqueado.bloqueado("ana@mail.com")
    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id is None
    assert len(avisos_enviados) == 2

    # Stripe reentrega el `reinstated`: no repone de nuevo ni avisa otra vez.
    assert _disputa(client, tipo="charge.dispute.funds_reinstated").status_code == 200

    assert _restante(compra_acreditada.account) == 1
    assert len(avisos_enviados) == 2


def test_el_withdrawn_reentregado_tras_el_reinstate_no_vuelve_a_marcar_ni_bloquear(
    client, compra_acreditada, avisos_enviados,
):
    """Stripe reentrega el `funds_withdrawn` DESPUÉS del `reinstated`: la
    disputa ya se cerró a favor, así que no se vuelve a marcar la fila, no se
    bloquea el mail otra vez ni se avisa. El ledger ya era idempotente por
    `external_id`; lo que faltaba era no tocar la marca ni el bloqueo."""
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")
    antes = len(avisos_enviados)

    r = _disputa(client)

    assert r.status_code == 200
    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id is None
    assert not MailBloqueado.bloqueado("ana@mail.com")
    assert _restante(compra_acreditada.account) == 1
    assert compra_acreditada.reembolsado_centavos == 14900
    assert len(avisos_enviados) == antes


def test_reinstated_sin_retiro_previo_solo_avisa(client, compra_acreditada, avisos_enviados):
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert _restante(compra_acreditada.account) == 1
    assert len(avisos_enviados) == 1
    assert "sin retiro previo" in avisos_enviados[0]


def test_el_completed_reentregado_tras_el_reinstate_no_entrega_ni_avisa_disputa(
    client, monkeypatch, compra_acreditada, avisos_enviados,
):
    """Después del `reinstated` la fila ya no está disputada: una reentrega
    del pago no puede decir «compra ya disputada», y tampoco otorgar otra vez."""
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")
    antes = len(avisos_enviados)
    sesion = {
        "id": "cs_du", "payment_status": "paid", "currency": "brl", "amount_subtotal": 14900,
        "amount_total": 14900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
    cuerpo = json.dumps({"id": "evt_c", "type": "checkout.session.completed", "data": {"object": {"id": "cs_du"}}}).encode()

    r = client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    assert r.status_code == 200
    assert _restante(compra_acreditada.account) == 1
    assert not any("disputada" in a for a in avisos_enviados[antes:])


def test_una_disputa_sobre_una_compra_ya_reembolsada_no_revoca_de_nuevo(client, compra_acreditada, avisos_enviados):
    """Reembolso total primero, disputa después: revocar otra vez dejaría
    deuda por un producto que ya se devolvió, y el contador sumaría dos."""
    from api.canje import revocar

    revocar(compra_acreditada.account, "informe_natal", 1, external_id="stripe:refund:re_1")
    PasarelaCheckout.objects.filter(pk=compra_acreditada.pk).update(reembolsado_centavos=14900)

    assert _disputa(client).status_code == 200

    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id == "du_1"
    assert compra_acreditada.reembolsado_centavos == 14900
    assert not Movimiento.objects.filter(external_id="stripe:dispute:du_1").exists()
    assert MailBloqueado.bloqueado("ana@mail.com")
    assert any("ya reembolsada" in a and "du_1" in a for a in avisos_enviados)


def test_una_disputa_en_otra_moneda_no_revoca_y_avisa(client, compra_acreditada, avisos_enviados):
    _disputa(client, currency="usd", amount=14900)

    assert _restante(compra_acreditada.account) == 1
    assert any("usd" in a for a in avisos_enviados)


def test_disputa_antes_de_completed_marca_la_fila_y_el_pago_no_entrega(client, monkeypatch, make_account, make_chart, avisos_enviados):
    """EC16: el PI todavía no está en la fila; se resuelve por la sesión."""
    cuenta = make_account(email="ana@mail.com")
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_du", account=cuenta, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900, sujeto=sujeto_natal(make_chart(account=cuenta)),
    )
    monkeypatch.setattr(stripe_client, "sesion_por_payment_intent", lambda pi: {"id": "cs_du"} if pi == "pi_1" else None)
    monkeypatch.setattr(disputas, "sesion_por_payment_intent", lambda pi: {"id": "cs_du"} if pi == "pi_1" else None)

    _disputa(client)
    fila.refresh_from_db()
    assert fila.disputa_id == "du_1"

    sesion = {
        "id": "cs_du", "payment_status": "paid", "currency": "brl", "amount_subtotal": 14900,
        "amount_total": 14900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
    cuerpo = json.dumps({"id": "evt_c", "type": "checkout.session.completed", "data": {"object": {"id": "cs_du"}}}).encode()
    client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    assert _restante(cuenta) == 0
    fila.refresh_from_db()
    assert fila.acreditado_at is None


def test_una_disputa_sin_compra_conocida_avisa_y_no_toca_nada(client, monkeypatch, avisos_enviados):
    """Review Focus 4."""
    monkeypatch.setattr(disputas, "sesion_por_payment_intent", lambda pi: None)

    r = _disputa(client, payment_intent="pi_ajeno")

    assert r.status_code == 200
    assert any("pi_ajeno" in a for a in avisos_enviados)


def test_una_compra_anonima_de_un_mail_bloqueado_se_acredita_y_avisa(client, anonima, entregar_anonima, sin_hilo, avisos_enviados):
    """R8: la plata entró; se entrega y se avisa."""
    from tests.api.conftest import con_mail

    MailBloqueado.bloquear("ana@mail.com", motivo="disputa")

    r = entregar_anonima(con_mail("ana@mail.com"))

    assert r.status_code == 200
    assert PasarelaCheckout.objects.get(checkout_id=anonima.checkout_id).acreditado_at is not None
    assert any("bloqueado" in a.lower() and anonima.checkout_id in a and "a***@mail.com" in a for a in avisos_enviados)
    assert not any("ana@mail.com" in a for a in avisos_enviados)


def test_un_fallo_a_mitad_del_retiro_no_deja_la_disputa_marcada(client, monkeypatch, compra_acreditada, avisos_enviados):
    """Todo el retiro es un átomo: si `revocar` falla, la marca `disputa_id`
    se deshace con él y el reintento de Stripe aplica la disputa entera."""
    revocar_real = disputas.revocar
    llamadas = []

    def revocar_que_falla_una_vez(*args, **kwargs):
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("la base se cayó")
        return revocar_real(*args, **kwargs)

    monkeypatch.setattr(disputas, "revocar", revocar_que_falla_una_vez)

    assert _disputa(client).status_code == 500
    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id is None
    assert not MailBloqueado.bloqueado("ana@mail.com")

    assert _disputa(client).status_code == 200
    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id == "du_1"
    assert _restante(compra_acreditada.account) == 0
    assert MailBloqueado.bloqueado("ana@mail.com")
    assert len([a for a in avisos_enviados if "Revocado" in a]) == 1


def test_una_disputa_procesada_mientras_se_acredita_no_se_entrega(client, monkeypatch, make_account, avisos_enviados):
    """La marca se vuelve a mirar con la fila bloqueada, justo antes de
    otorgar: una disputa que entró entre el primer chequeo y la entrega no
    se pierde."""
    cuenta = make_account(email="ana@mail.com")
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_du", account=cuenta, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900,
    )
    sesion = {
        "id": "cs_du", "payment_status": "paid", "currency": "brl", "amount_subtotal": 14900,
        "amount_total": 14900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)

    def disputa_en_el_medio(*_args):
        PasarelaCheckout.objects.filter(pk=fila.pk).update(disputa_id="du_1")

    monkeypatch.setattr(webhooks_stripe, "_avisar_si_el_precio_no_lleva_el_impuesto_incluido", disputa_en_el_medio)
    cuerpo = json.dumps({"id": "evt_c", "type": "checkout.session.completed", "data": {"object": {"id": "cs_du"}}}).encode()
    r = client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    assert r.status_code == 200
    assert _restante(cuenta) == 0
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert any("du_1" in a for a in avisos_enviados)


def test_reinstated_con_la_cuenta_borrada_avisa_y_no_reintenta(client, compra_acreditada, avisos_enviados):
    _disputa(client)
    compra_acreditada.account.delete()

    r = _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert r.status_code == 200
    assert any("cuenta" in a.lower() and "du_1" in a for a in avisos_enviados[1:])
    assert not MailBloqueado.bloqueado("ana@mail.com")


def test_reinstated_desbloquea_aunque_la_cuenta_haya_cambiado_de_mail(client, compra_acreditada, avisos_enviados):
    _disputa(client)
    compra_acreditada.account.email = "nueva@mail.com"
    compra_acreditada.account.save(update_fields=["email"])

    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert not MailBloqueado.bloqueado("ana@mail.com")


def test_una_compra_anonima_disputada_antes_de_completed_bloquea_el_mail_del_pago(client, monkeypatch, make_chart, avisos_enviados):
    """EC16 sin cuenta: la fila todavía no tiene a quién; el mail sale de la
    sesión que Stripe devuelve para ese PaymentIntent."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_du", account=None, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900, anonimo=True, nonce_hash="x" * 64,
        sujeto=sujeto_natal(make_chart(account=None)),
    )
    monkeypatch.setattr(
        disputas, "sesion_por_payment_intent",
        lambda pi: {"id": "cs_du", "customer_details": {"email": " Ana@Mail.com "}},
    )

    assert _disputa(client).status_code == 200

    fila.refresh_from_db()
    assert fila.disputa_id == "du_1"
    assert MailBloqueado.bloqueado("ana@mail.com")


def test_el_reinstated_de_una_disputa_sobre_compra_reembolsada_no_repone(client, compra_acreditada, avisos_enviados):
    """El retiro no revocó (ya estaba reembolsada): reponer regalaría el
    producto a quien ya tiene la plata de vuelta."""
    from api.canje import revocar

    revocar(compra_acreditada.account, "informe_natal", 1, external_id="stripe:refund:re_1")
    PasarelaCheckout.objects.filter(pk=compra_acreditada.pk).update(reembolsado_centavos=14900)
    _disputa(client)

    assert _disputa(client, tipo="charge.dispute.funds_reinstated").status_code == 200

    assert _restante(compra_acreditada.account) == 0
    assert not Movimiento.objects.filter(external_id="stripe:dispute:du_1:reinstated").exists()
    assert not MailBloqueado.bloqueado("ana@mail.com")
    assert any("no se repone" in a for a in avisos_enviados)


# --- Revisión del 18-10-2026: la disputa tiene registro propio --------------


def _reembolsada_entera(fila):
    from api.canje import revocar

    revocar(fila.account, "informe_natal", 1, external_id="stripe:refund:re_1")
    PasarelaCheckout.objects.filter(pk=fila.pk).update(reembolsado_centavos=14900)


def test_resuelta_a_favor_sobre_compra_reembolsada_el_retiro_reentregado_no_vuelve_a_bloquear(
    client, compra_acreditada, avisos_enviados,
):
    """Sin registro propio de la disputa, sólo la rama «repuesto» dejaba
    constancia: en las otras, un `withdrawn` reentregado se aplicaba de nuevo."""
    _reembolsada_entera(compra_acreditada)
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")
    _disputa(client)

    compra_acreditada.refresh_from_db()
    assert compra_acreditada.disputa_id is None
    assert not MailBloqueado.bloqueado("ana@mail.com")


def test_resuelta_a_favor_sobre_compra_reembolsada_el_reinstate_reentregado_no_avisa_de_mas(
    client, compra_acreditada, avisos_enviados,
):
    _reembolsada_entera(compra_acreditada)
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert not any("sin retiro previo" in a for a in avisos_enviados)


@pytest.mark.parametrize("primera", ["du_1", "du_2"])
def test_con_dos_disputas_del_mismo_mail_sigue_bloqueado_hasta_resolver_las_dos(
    client, compra_acreditada, avisos_enviados, primera,
):
    from django.utils import timezone

    from api.canje import aplicar_compra

    cuenta = compra_acreditada.account
    PasarelaCheckout.objects.create(
        checkout_id="cs_du2", account=cuenta, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900, payment_intent="pi_2", acreditado_at=timezone.now(),
    )
    aplicar_compra(cuenta, "informe_natal", 14900, external_id="stripe:session:cs_du2", precio_centavos=14900)
    pi = {"du_1": "pi_1", "du_2": "pi_2"}
    _disputa(client, id="du_1", payment_intent="pi_1")
    _disputa(client, id="du_2", payment_intent="pi_2")

    segunda = "du_2" if primera == "du_1" else "du_1"
    _disputa(client, tipo="charge.dispute.funds_reinstated", id=primera, payment_intent=pi[primera])
    assert MailBloqueado.bloqueado("ana@mail.com")

    _disputa(client, tipo="charge.dispute.funds_reinstated", id=segunda, payment_intent=pi[segunda])
    assert not MailBloqueado.bloqueado("ana@mail.com")


def test_un_bloqueo_puesto_a_mano_no_lo_levanta_una_disputa_resuelta(client, compra_acreditada, avisos_enviados):
    MailBloqueado.bloquear("ana@mail.com", motivo="a mano")
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert MailBloqueado.bloqueado("ana@mail.com")


def test_reembolso_parcial_y_despues_disputa_no_revoca_dos_veces_ni_anota_de_mas(
    client, compra_acreditada, avisos_enviados,
):
    """El parcial ya revocó la única unidad (no existe medio informe)."""
    from api.canje import revocar

    revocar(compra_acreditada.account, "informe_natal", 1, external_id="stripe:refund:re_p")
    PasarelaCheckout.objects.filter(pk=compra_acreditada.pk).update(reembolsado_centavos=5000)

    _disputa(client, amount=14900)

    compra_acreditada.refresh_from_db()
    assert compra_acreditada.reembolsado_centavos == 14900
    assert not Movimiento.objects.filter(external_id="stripe:dispute:du_1").exists()
    assert MailBloqueado.bloqueado("ana@mail.com")


def test_pack_con_reembolso_parcial_la_disputa_revoca_solo_lo_que_queda(
    client, make_account, avisos_enviados,
):
    from django.utils import timezone

    from api.canje import aplicar_compra, revocar

    cuenta = make_account(email="ana@mail.com")
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_pack", account=cuenta, codigo_producto="pack_5_natal", moneda="usd",
        precio_centavos=12500, payment_intent="pi_1", acreditado_at=timezone.now(),
    )
    aplicar_compra(cuenta, "pack_5_natal", 12500, external_id="stripe:session:cs_pack", precio_centavos=12500)
    # 2500 de 12500 es una unidad de cinco, como la revoca `_reembolsar`.
    revocar(cuenta, "informe_natal", 1, external_id="stripe:refund:re_p")
    PasarelaCheckout.objects.filter(pk=fila.pk).update(reembolsado_centavos=2500)
    assert _restante(cuenta) == 4

    _disputa(client, amount=10000, currency="usd")

    fila.refresh_from_db()
    assert _restante(cuenta) == 0
    assert fila.reembolsado_centavos == 12500
    saldo = Derecho.objects.get(account=cuenta, codigo_producto="informe_natal")
    assert saldo.cantidad_restante == 0


def test_disputa_antes_del_pago_resuelta_a_favor_el_pago_que_llega_se_entrega_y_el_aviso_lo_dice(
    client, monkeypatch, make_account, make_chart, avisos_enviados, sin_hilo,
):
    cuenta = make_account(email="ana@mail.com")
    PasarelaCheckout.objects.create(
        checkout_id="cs_du", account=cuenta, codigo_producto="informe_natal", moneda="brl",
        precio_centavos=14900, sujeto=sujeto_natal(make_chart(account=cuenta)),
    )
    monkeypatch.setattr(disputas, "sesion_por_payment_intent", lambda pi: {"id": "cs_du"} if pi == "pi_1" else None)
    _disputa(client)
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert any("du_1" in a and "se entrega solo" in a for a in avisos_enviados)

    sesion = {
        "id": "cs_du", "payment_status": "paid", "currency": "brl", "amount_subtotal": 14900,
        "amount_total": 14900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
    cuerpo = json.dumps({"id": "evt_c", "type": "checkout.session.completed", "data": {"object": {"id": "cs_du"}}}).encode()
    client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    # Entregada: el informe arranca solo y consume el derecho (sin_hilo).
    fila = PasarelaCheckout.objects.get(checkout_id="cs_du")
    assert fila.acreditado_at is not None
    assert fila.disputa_id is None
