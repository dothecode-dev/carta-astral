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


@pytest.fixture
def make_account(db):
    def _make(free_balance=None, paid_balance=0):
        from django.conf import settings
        from api.models import Account
        fb = settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
        return Account.objects.create(free_balance=fb, paid_balance=paid_balance)
    return _make


@pytest.fixture
def account_client(make_account):
    from api.auth import create_session
    acc = make_account()
    token = create_session(acc)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.account = acc
    return client
