import pytest
from django.core.management import call_command

from api.identity import new_token
from api.models import Installation

pytestmark = pytest.mark.django_db


def test_grant_credits_adds_to_purchased():
    _, h = new_token()
    inst = Installation.objects.create(token_hash=h)
    call_command("grant_credits", str(inst.id), "5")
    inst.refresh_from_db()
    assert inst.purchased_credits == 5
