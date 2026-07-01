import pytest
from django.db import IntegrityError


@pytest.mark.django_db
def test_credit_transaction_external_id_unique_when_present(make_account):
    from api.models import CreditTransaction
    acc = make_account()
    CreditTransaction.objects.create(account=acc, kind="purchase", lot="paid", amount=5, external_id="evt_1")
    with pytest.raises(IntegrityError):
        CreditTransaction.objects.create(account=acc, kind="purchase", lot="paid", amount=5, external_id="evt_1")


@pytest.mark.django_db
def test_blank_external_id_not_deduped(make_account):
    # Las txns internas (consumption, free_grant) no llevan external_id y no deben chocar.
    from api.models import CreditTransaction
    acc = make_account()
    CreditTransaction.objects.create(account=acc, kind="consumption", lot="free", amount=-1)
    CreditTransaction.objects.create(account=acc, kind="consumption", lot="free", amount=-1)  # no explota


@pytest.mark.django_db
def test_paid_balance_can_go_negative(make_account):
    acc = make_account(paid_balance=0)
    acc.paid_balance = -3
    acc.save(update_fields=["paid_balance"])
    acc.refresh_from_db()
    assert acc.paid_balance == -3
