import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_grant_credits_adds_to_paid_balance():
    from api.models import Account

    acc = Account.objects.create()
    call_command("grant_credits", str(acc.id), "5")
    acc.refresh_from_db()
    assert acc.paid_balance == 5
    assert acc.credit_txns.filter(kind="purchase", amount=5).count() == 1


@pytest.mark.django_db
def test_grant_credits_unknown_account():
    with pytest.raises(CommandError):
        call_command("grant_credits", "999999", "1")
