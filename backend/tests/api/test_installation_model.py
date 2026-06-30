import pytest

from api.identity import hash_token, new_token
from api.models import Installation

pytestmark = pytest.mark.django_db


def test_new_token_returns_clear_and_hash():
    clear, h = new_token()
    assert clear and h
    assert h == hash_token(clear)
    assert clear != h  # no se guarda en claro


def test_installation_defaults():
    _, h = new_token()
    inst = Installation.objects.create(token_hash=h)
    assert inst.purchased_credits == 0
    assert inst.created_at is not None
