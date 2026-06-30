import pytest
from django.utils import timezone


@pytest.mark.django_db
def test_session_belongs_to_account_and_has_expiry():
    from api.models import Account, Session

    acc = Account.objects.create()
    s = Session.objects.create(
        token_hash="abc", account=acc,
        expires_at=timezone.now() + timezone.timedelta(days=1),
    )
    assert s in acc.sessions.all()
    assert s.expires_at > timezone.now()
