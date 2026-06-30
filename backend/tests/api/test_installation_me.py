import pytest
from rest_framework.test import APIClient

from api.identity import new_token
from api.models import Installation

pytestmark = pytest.mark.django_db


def test_me_returns_available_credits():
    clear, h = new_token()
    Installation.objects.create(token_hash=h, purchased_credits=2)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {clear}")
    resp = c.get("/api/installations/me/")
    assert resp.status_code == 200
    assert resp.json()["credits_available"] == 3  # 1 free + 2 purchased


def test_me_requires_token():
    assert APIClient().get("/api/installations/me/").status_code == 401
