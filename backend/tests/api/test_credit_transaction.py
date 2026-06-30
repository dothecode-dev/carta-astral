import pytest


@pytest.mark.django_db
def test_credit_transaction_records_movement():
    from api.models import Account, CreditTransaction

    acc = Account.objects.create()
    tx = CreditTransaction.objects.create(
        account=acc, kind="free_grant", lot="free", amount=1,
    )
    assert tx in acc.credit_txns.all()
    assert tx.amount == 1


@pytest.mark.django_db
def test_chart_and_interpretation_have_account():
    from api.models import Account, BirthData, Chart, Interpretation

    acc = Account.objects.create()
    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    ch = Chart.objects.create(birth_data=bd, data={}, engine_version="x", account=acc)
    interp = Interpretation.objects.create(
        chart=ch, lang="es", prompt_version="v1", text="t", account=acc,
    )
    assert ch in acc.charts.all()
    assert interp in acc.interpretations.all()
