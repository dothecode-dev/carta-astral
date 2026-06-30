import pytest
from django.core.management import call_command
from django.utils import timezone


@pytest.mark.django_db
def test_purge_removes_only_expired():
    from api.models import Account, Session

    acc = Account.objects.create()
    Session.objects.create(token_hash="live", account=acc,
                           expires_at=timezone.now() + timezone.timedelta(days=1))
    Session.objects.create(token_hash="dead", account=acc,
                           expires_at=timezone.now() - timezone.timedelta(days=1))
    call_command("purge_sessions")
    assert Session.objects.filter(token_hash="live").exists()
    assert not Session.objects.filter(token_hash="dead").exists()
