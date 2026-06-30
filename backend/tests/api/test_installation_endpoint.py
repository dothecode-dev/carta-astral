import pytest
from rest_framework.test import APIClient

from api.identity import hash_token
from api.models import Installation

pytestmark = pytest.mark.django_db


def test_register_creates_installation_and_returns_token():
    resp = APIClient().post("/api/installations/")
    assert resp.status_code == 201
    body = resp.json()
    assert body["credits_available"] == 3
    token = body["token"]
    assert Installation.objects.filter(token_hash=hash_token(token)).exists()
