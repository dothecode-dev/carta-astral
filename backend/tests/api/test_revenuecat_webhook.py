# backend/tests/api/test_revenuecat_webhook.py
import pytest
from rest_framework.test import APIClient

URL = "/api/webhooks/revenuecat"


def _event(**over):
    ev = {"type": "NON_RENEWING_PURCHASE", "id": "evt_1",
          "app_user_id": "1", "product_id": "credits_10",
          "store": "APP_STORE", "environment": "PRODUCTION"}
    ev.update(over)
    return {"api_version": "1.0", "event": ev}


@pytest.fixture
def cfg(settings):
    settings.REVENUECAT_WEBHOOK_AUTH = "secret-abc"
    settings.REVENUECAT_PRODUCT_CREDITS = {"credits_10": 10}
    settings.REFUND_FLAG_THRESHOLD = 3
    return settings


@pytest.mark.django_db
def test_rejects_bad_auth(cfg, make_account):
    acc = make_account()
    r = APIClient().post(URL, _event(app_user_id=str(acc.id)), format="json",
                         HTTP_AUTHORIZATION="wrong")
    assert r.status_code == 401


@pytest.mark.django_db
def test_purchase_credits_account(cfg, make_account):
    acc = make_account(paid_balance=0)
    r = APIClient().post(URL, _event(app_user_id=str(acc.id)), format="json",
                         HTTP_AUTHORIZATION="secret-abc")
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 10


@pytest.mark.django_db
def test_purchase_idempotent_on_retry(cfg, make_account):
    acc = make_account(paid_balance=0)
    c = APIClient()
    body = _event(app_user_id=str(acc.id), id="evt_dup")
    c.post(URL, body, format="json", HTTP_AUTHORIZATION="secret-abc")
    c.post(URL, body, format="json", HTTP_AUTHORIZATION="secret-abc")  # reintento
    acc.refresh_from_db()
    assert acc.paid_balance == 10  # una sola vez


@pytest.mark.django_db
def test_refund_clawbacks(cfg, make_account):
    acc = make_account(paid_balance=10)
    r = APIClient().post(URL, _event(type="CANCELLATION", id="rf_1", app_user_id=str(acc.id)),
                         format="json", HTTP_AUTHORIZATION="secret-abc")
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 0
    assert acc.refund_count == 1


@pytest.mark.django_db
def test_unknown_account_acked_not_credited(cfg):
    r = APIClient().post(URL, _event(app_user_id="999999"), format="json",
                         HTTP_AUTHORIZATION="secret-abc")
    assert r.status_code == 200  # ack para cortar reintentos


@pytest.mark.django_db
def test_unknown_product_acked(cfg, make_account):
    acc = make_account(paid_balance=0)
    r = APIClient().post(URL, _event(app_user_id=str(acc.id), product_id="mystery"),
                         format="json", HTTP_AUTHORIZATION="secret-abc")
    assert r.status_code == 200
    acc.refresh_from_db()
    assert acc.paid_balance == 0


@pytest.mark.django_db
def test_empty_secret_rejects(settings, make_account):
    settings.REVENUECAT_WEBHOOK_AUTH = ""
    settings.REVENUECAT_PRODUCT_CREDITS = {"credits_10": 10}
    acc = make_account()
    r = APIClient().post(URL, _event(app_user_id=str(acc.id)), format="json",
                         HTTP_AUTHORIZATION="")
    assert r.status_code == 401


@pytest.mark.django_db
def test_non_numeric_app_user_id_acked(cfg):
    r = APIClient().post(URL, _event(app_user_id="$RCAnonymousID:abc123"),
                         format="json", HTTP_AUTHORIZATION="secret-abc")
    assert r.status_code == 200
