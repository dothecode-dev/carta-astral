"""Blindaje del webhook: nadie vio nunca un payload REAL de RevenueCat.

Dos objetivos:
  1. Que un cambio de nombre de campo no haga perder una compra pagada.
  2. Que cuando un evento se ignore quede en el log su ESTRUCTURA (las claves,
     nunca los valores) para poder corregir sin adivinar y sin filtrar datos
     del comprador.
"""

import pytest
from rest_framework.test import APIClient

URL = "/api/webhooks/revenuecat"
AUTH = "secret-abc"


@pytest.fixture
def cfg(settings):
    # Apagado por defecto sin app (ver `test_modo_web.py`): acá se prueba el
    # comportamiento encendido, que no puede degradarse mientras duerme.
    settings.IAP_WEBHOOK_ENABLED = True
    settings.REVENUECAT_WEBHOOK_AUTH = AUTH
    settings.REVENUECAT_PRODUCT_CREDITS = {"credits_10": 10}
    settings.REFUND_FLAG_THRESHOLD = 3
    return settings


def _post(payload):
    return APIClient().post(URL, payload, format="json", HTTP_AUTHORIZATION=AUTH)


@pytest.mark.django_db
def test_acredita_con_event_id_en_vez_de_id(cfg, make_account):
    """Si el id del evento viniera como `event_id`, la compra no puede perderse."""
    acc = make_account(paid_balance=0)
    r = _post({"event": {
        "type": "NON_RENEWING_PURCHASE", "event_id": "evt_alt",
        "app_user_id": str(acc.id), "product_id": "credits_10",
    }})
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10


@pytest.mark.django_db
def test_acredita_con_product_identifier(cfg, make_account):
    acc = make_account(paid_balance=0)
    r = _post({"event": {
        "type": "NON_RENEWING_PURCHASE", "id": "evt_2",
        "app_user_id": str(acc.id), "product_identifier": "credits_10",
    }})
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10


@pytest.mark.django_db
def test_acredita_con_original_app_user_id(cfg, make_account):
    """RevenueCat manda original_app_user_id cuando hubo alias de usuario."""
    acc = make_account(paid_balance=0)
    r = _post({"event": {
        "type": "NON_RENEWING_PURCHASE", "id": "evt_3",
        "original_app_user_id": str(acc.id), "product_id": "credits_10",
    }})
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10


@pytest.mark.django_db
def test_la_idempotencia_sigue_valiendo_con_los_alias(cfg, make_account):
    """El mismo evento por event_id no puede acreditar dos veces."""
    acc = make_account(paid_balance=0)
    payload = {"event": {
        "type": "NON_RENEWING_PURCHASE", "event_id": "evt_dup",
        "app_user_id": str(acc.id), "product_id": "credits_10",
    }}
    assert _post(payload).status_code == 200
    assert _post(payload).status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10  # una sola vez


@pytest.mark.django_db
def test_evento_ignorado_loguea_la_estructura_sin_valores(cfg, caplog):
    """Lo que permite corregir el mapeo sin exponer datos del comprador."""
    with caplog.at_level("WARNING"):
        r = _post({"event": {
            "type": "UNKNOWN_KIND",
            "id": "evt_x",
            "app_user_id": "999999",
            "aliases": ["a@b.com"],
            "subscriber_attributes": {"$email": {"value": "comprador@ejemplo.com"}},
        }})
    assert r.status_code == 200

    log = " ".join(r.message for r in caplog.records)
    # las claves sí, para poder mapear
    assert "subscriber_attributes" in log
    assert "aliases" in log
    # los valores NO
    assert "comprador@ejemplo.com" not in log
    assert "a@b.com" not in log


@pytest.mark.django_db
def test_product_sin_mapeo_loguea_estructura_y_el_product_id(cfg, make_account, caplog):
    """El product_id sí es útil en el log (no es dato personal) para arreglar el mapa."""
    acc = make_account()
    with caplog.at_level("WARNING"):
        r = _post({"event": {
            "type": "NON_RENEWING_PURCHASE", "id": "evt_4",
            "app_user_id": str(acc.id), "product_id": "credits_999",
        }})
    assert r.status_code == 200
    log = " ".join(r.message for r in caplog.records)
    assert "credits_999" in log


@pytest.mark.django_db
def test_cancellation_queda_registrada_aunque_no_descuente(cfg, make_account, caplog):
    """CANCELLATION se excluyó del clawback a propósito; que al menos se vea."""
    acc = make_account(paid_balance=10)
    with caplog.at_level("INFO"):
        r = _post({"event": {
            "type": "CANCELLATION", "id": "evt_5",
            "app_user_id": str(acc.id), "product_id": "credits_10",
        }})
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10  # no se toca el saldo
    assert any("CANCELLATION" in r.message for r in caplog.records)
