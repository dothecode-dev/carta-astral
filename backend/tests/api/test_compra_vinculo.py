import json

import pytest
from django.db import connection

from api import stripe_client, webhooks_stripe
from api.models import Interpretation, Movimiento, PasarelaCheckout
from api.vinculo_service import crear_vinculo
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
PRECIO = "price_vinculo"
SESSION = "cs_test_vinculo"
PI = "pi_vinculo"
A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time_known": False, "lat": -31.42, "lng": -64.18}


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.VINCULO_ENABLED = True
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {PRECIO: "informe_vinculo"}
    monkeypatch.setattr(stripe_client, "crear_checkout",
                        lambda *a, **k: (SESSION, "https://checkout.stripe.test/x"))


@pytest.fixture
def vinculo(account):
    return crear_vinculo(account, "amistad", [A, B])


@pytest.fixture
def fila(vinculo):
    return PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=vinculo.account, codigo_producto="informe_vinculo",
        sujeto=vinculo, locale="es", precio_centavos=900,
    )


def _post_firmado(client, evento: dict):
    cuerpo = json.dumps(evento).encode()
    return client.post(URL, data=cuerpo, content_type="application/json",
                       HTTP_STRIPE_SIGNATURE=firmar(cuerpo))


def _pagar(client, monkeypatch):
    sesion = {
        "id": SESSION, "payment_status": "paid", "amount_subtotal": 900, "amount_total": 900,
        "total_details": {"amount_tax": 0, "amount_discount": 0}, "payment_intent": PI,
        "metadata": {}, "line_items": {"data": [{"price": {"id": PRECIO}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda session_id: sesion)
    return _post_firmado(client, {"id": "evt_v", "type": "checkout.session.completed",
                                  "data": {"object": {"id": SESSION, "object": "checkout.session"}}})


def test_checkout_de_vinculo_guarda_el_sujeto(client_autenticado, vinculo):
    r = client_autenticado.post(
        "/api/checkout/", {"producto": "informe_vinculo", "vinculo_id": str(vinculo.uuid)}, format="json",
    )
    assert r.status_code == 200
    assert PasarelaCheckout.objects.get().sujeto == vinculo


def test_un_natal_contra_un_vinculo_es_400(client_autenticado, vinculo):
    r = client_autenticado.post(
        "/api/checkout/", {"producto": "informe_natal", "vinculo_id": str(vinculo.uuid)}, format="json",
    )
    assert r.status_code == 400


def test_con_el_flag_apagado_es_400(client_autenticado, vinculo, settings):
    settings.VINCULO_ENABLED = False
    r = client_autenticado.post(
        "/api/checkout/", {"producto": "informe_vinculo", "vinculo_id": str(vinculo.uuid)}, format="json",
    )
    assert r.status_code == 400


def test_el_webhook_acredita_y_arranca_el_vinculo(client, monkeypatch, fila, sin_hilo):
    assert _pagar(client, monkeypatch).status_code == 200
    fila.refresh_from_db()
    assert fila.acreditado_at is not None
    assert Interpretation.objects.filter(sujeto=fila.sujeto, tier="largo").exists()
    assert Movimiento.objects.filter(
        sujeto=fila.sujeto, tipo="consumo", codigo_producto="informe_vinculo",
    ).count() == 1


def test_el_estado_manda_a_la_pagina_del_vinculo(client, client_autenticado, monkeypatch, fila, sin_hilo):
    _pagar(client, monkeypatch)
    r = client_autenticado.get(f"/api/checkout/{SESSION}/")
    assert r.data["destino"] == {"tipo": "vinculo", "id": str(fila.sujeto.uuid)}


@pytest.mark.skipif(connection.vendor != "postgresql", reason="reembolso: Postgres (RF11)")
def test_el_reembolso_de_un_vinculo_revoca_como_el_natal(client, monkeypatch, fila, sin_hilo):
    _pagar(client, monkeypatch)
    refund = {"id": "re_v", "object": "refund", "amount": 900, "currency": "usd",
              "charge": "ch_v", "payment_intent": PI, "reason": None, "status": "succeeded"}
    assert _post_firmado(client, {"id": "evt_rv", "type": "refund.created",
                                  "data": {"object": refund}}).status_code == 200
    assert Movimiento.objects.filter(tipo="revocacion", codigo_producto="informe_vinculo").exists()
