import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory


@pytest.mark.django_db
def test_valid_session_authenticates_account():
    from api.auth import AccountTokenAuthentication, create_session
    from api.models import Account

    acc = Account.objects.create()
    token = create_session(acc)
    req = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {token}")
    user, auth = AccountTokenAuthentication().authenticate(req)
    assert user.id == acc.id


@pytest.mark.django_db
def test_expired_session_rejected():
    from rest_framework.exceptions import AuthenticationFailed
    from api.auth import AccountTokenAuthentication
    from api.identity import new_token
    from api.models import Account, Session

    acc = Account.objects.create()
    clear, h = new_token()
    Session.objects.create(
        token_hash=h, account=acc, expires_at=timezone.now() - timezone.timedelta(days=1),
    )
    req = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {clear}")
    with pytest.raises(AuthenticationFailed):
        AccountTokenAuthentication().authenticate(req)


@pytest.mark.django_db
def test_has_account_permission():
    from api.models import Account
    from api.permissions import HasAccount

    class _Req:
        auth = Account.objects.create()
    assert HasAccount().has_permission(_Req(), None) is True
