import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_delete_account_command():
    from api.models import Account

    acc = Account.objects.create()
    call_command("delete_account", str(acc.id))
    assert not Account.objects.filter(pk=acc.pk).exists()


@pytest.mark.django_db
def test_delete_account_unknown():
    with pytest.raises(CommandError):
        call_command("delete_account", "999999")
