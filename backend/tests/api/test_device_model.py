import pytest


@pytest.mark.django_db
def test_device_can_be_accountless():
    from api.models import Device

    d = Device.objects.create(platform="ios")
    assert d.account is None


@pytest.mark.django_db
def test_device_links_to_account():
    from api.models import Account, Device

    acc = Account.objects.create()
    d = Device.objects.create(platform="android", account=acc)
    assert d in acc.devices.all()
