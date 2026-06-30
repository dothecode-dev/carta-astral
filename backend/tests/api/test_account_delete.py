import pytest
from django.conf import settings
from rest_framework.test import APIClient
from api.auth import create_session
from api.models import Account, SubTombstone
from api.identity import sub_hash
from api.sso import VerifiedIdentity


@pytest.mark.django_db
def test_delete_account_endpoint_revokes_and_tombstones():
    from api.accounts import resolve_account

    acc = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    # gastar la free
    acc.free_balance = 0
    acc.save()
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert c.delete("/api/account/").status_code == 204
    # token revocado
    assert c.get("/api/account/").status_code in (401, 403)
    # tombstone con free consumido
    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "S"))
    assert tomb.free_credits_consumed == settings.INSTALL_FREE_CREDITS
    # cuenta borrada
    assert not Account.objects.filter(pk=acc.pk).exists()


@pytest.mark.django_db
def test_recreate_after_delete_has_no_free():
    from api.accounts import resolve_account

    acc = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    acc.free_balance = 0
    acc.save()
    from api.deletion import delete_account
    delete_account(acc)
    again = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    assert again.free_balance == 0


@pytest.mark.django_db
def test_unauthenticated_delete_rejected():
    assert APIClient().delete("/api/account/").status_code in (401, 403)
