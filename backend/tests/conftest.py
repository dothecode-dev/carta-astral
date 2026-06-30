import pytest
from rest_framework.test import APIClient


@pytest.fixture
def make_installation(db):
    def _make(purchased_credits=0):
        from api.identity import new_token
        from api.models import Installation

        clear, h = new_token()
        inst = Installation.objects.create(token_hash=h, purchased_credits=purchased_credits)
        return clear, inst

    return _make


@pytest.fixture
def auth_client(make_installation):
    clear, inst = make_installation()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {clear}")
    client.installation = inst
    return client
