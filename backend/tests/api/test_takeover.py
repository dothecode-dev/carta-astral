import pytest
from api.sso import VerifiedIdentity


@pytest.mark.django_db
def test_unverified_email_does_not_link_to_existing_account():
    from api.accounts import resolve_account

    victim = resolve_account(
        VerifiedIdentity("apple", "VICTIM", "victim@x.com", True)
    )
    attacker = resolve_account(
        VerifiedIdentity("google", "ATTACKER", "victim@x.com", False)  # email NO verificado
    )
    assert attacker.id != victim.id  # no se linkeó a la cuenta de la víctima
