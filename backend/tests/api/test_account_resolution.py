from unittest import mock

import pytest
from django.conf import settings
from api.sso import VerifiedIdentity


def _vid(provider="apple", sub="S", email="u@x.com", verified=True):
    return VerifiedIdentity(provider=provider, sub=sub, email=email, email_verified=verified)


@pytest.mark.django_db
def test_same_sub_returns_same_account():
    from api.accounts import resolve_account

    a = resolve_account(_vid())
    b = resolve_account(_vid())
    assert a.id == b.id


@pytest.mark.django_db
def test_links_by_verified_email_across_providers():
    from api.accounts import resolve_account

    apple = resolve_account(_vid(provider="apple", sub="A", email="same@x.com"))
    google = resolve_account(_vid(provider="google", sub="G", email="same@x.com"))
    assert apple.id == google.id
    assert apple.identities.count() == 2


@pytest.mark.django_db
def test_new_sub_with_tombstone_starts_without_free():
    from api.accounts import resolve_account
    from api.identity import sub_hash
    from api.models import SubTombstone

    SubTombstone.objects.create(
        sub_hash=sub_hash("apple", "S"), free_credits_consumed=settings.INSTALL_FREE_CREDITS,
    )
    acc = resolve_account(_vid(provider="apple", sub="S"))
    assert acc.free_balance == 0
    assert acc.paid_balance == 0


@pytest.mark.django_db
def test_concurrent_create_of_same_new_sub_does_not_duplicate():
    """Race safety: si un login paralelo del mismo sub gana la carrera, el
    segundo no debe crear cuenta/identidad duplicada ni explotar: re-lee y
    devuelve la cuenta ganadora. Simula el ganador commiteado (autocommit)
    enganchando el lookup de tombstone, que corre antes del bloque atomic."""
    import api.accounts as accounts
    from api.identity import sub_hash as real_sub_hash
    from api.models import Account, ProviderIdentity

    def hook(provider, sub):
        h = real_sub_hash(provider, sub)
        if not ProviderIdentity.objects.filter(provider=provider, sub=sub).exists():
            winner = Account.objects.create(email="winner@x.com")
            ProviderIdentity.objects.create(provider=provider, sub=sub, account=winner)
        return h

    with mock.patch.object(accounts, "sub_hash", side_effect=hook):
        result = accounts.resolve_account(_vid(provider="apple", sub="RACE", email=""))

    assert ProviderIdentity.objects.filter(provider="apple", sub="RACE").count() == 1
    assert result.email == "winner@x.com"
    assert Account.objects.count() == 1  # nuestro intento se rollbackeo, sin huerfana


@pytest.mark.django_db
def test_new_sub_without_tombstone_gets_free_grant():
    from api.accounts import resolve_account
    from api.models import CreditTransaction

    acc = resolve_account(_vid())
    assert acc.free_balance == settings.INSTALL_FREE_CREDITS
    assert CreditTransaction.objects.filter(account=acc, kind="free_grant").count() == 1
