import pytest
from django.conf import settings


@pytest.mark.django_db
def test_account_defaults():
    from api.models import Account

    acc = Account.objects.create()
    assert acc.free_balance == settings.INSTALL_FREE_CREDITS
    assert acc.paid_balance == 0
    assert acc.email == "" or acc.email is None
    assert acc.email_verified is False
    assert acc.is_authenticated is True
    assert acc.is_anonymous is False
