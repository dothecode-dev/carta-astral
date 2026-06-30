import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_account_me_returns_credits():
    from api.auth import create_session
    from api.models import Account

    acc = Account.objects.create()
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = c.get("/api/account/")
    assert resp.status_code == 200
    assert resp.data["credits_available"] == 1
    assert resp.data["account_id"] == acc.id
