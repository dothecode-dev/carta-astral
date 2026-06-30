import pytest
from django.db import IntegrityError


@pytest.mark.django_db
def test_provider_sub_unique():
    from api.models import Account, ProviderIdentity

    a1 = Account.objects.create()
    a2 = Account.objects.create()
    ProviderIdentity.objects.create(provider="apple", sub="X", account=a1)
    with pytest.raises(IntegrityError):
        ProviderIdentity.objects.create(provider="apple", sub="X", account=a2)


@pytest.mark.django_db
def test_account_can_have_two_providers():
    from api.models import Account, ProviderIdentity

    a = Account.objects.create()
    ProviderIdentity.objects.create(provider="apple", sub="A", account=a)
    ProviderIdentity.objects.create(provider="google", sub="G", account=a)
    assert a.identities.count() == 2
