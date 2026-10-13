"""Disputas (RF15, EC11, EC16, Review Focus 4). Payload MEDIDO el 13-10-2026:
`charge.dispute.funds_withdrawn` trae `id`, `charge`, `payment_intent`,
`amount`, `currency`, `reason`, y puede llegar ANTES que `completed`."""

import json

import pytest

from api import stripe_client, webhooks_stripe
from api.models import Derecho, MailBloqueado, PasarelaCheckout
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
    assert any("du_1" in a and "brl" in a and "ana@mail.com" in a for a in avisos_enviados)


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


def test_reinstated_sin_retiro_previo_solo_avisa(client, compra_acreditada, avisos_enviados):
    _disputa(client, tipo="charge.dispute.funds_reinstated")

    assert _restante(compra_acreditada.account) == 1
    assert avisos_enviados


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
    monkeypatch.setattr(webhooks_stripe, "sesion_por_payment_intent", lambda pi: {"id": "cs_du"} if pi == "pi_1" else None)

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
    monkeypatch.setattr(webhooks_stripe, "sesion_por_payment_intent", lambda pi: None)

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
    assert any("bloqueado" in a.lower() for a in avisos_enviados)
