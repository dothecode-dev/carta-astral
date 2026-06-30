import pytest
from rest_framework.test import APIClient


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
