import pytest


def _make_interp(chart):
    def _factory():
        from api.models import Interpretation
        return Interpretation.objects.create(
            chart=chart, lang="es", prompt_version="v1", text="t", account=chart.account,
        )
    return _factory


@pytest.fixture
def chart(db):
    from api.models import Account, BirthData, Chart
    acc = Account.objects.create()  # free_balance=1 por default
    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    return Chart.objects.create(birth_data=bd, data={}, engine_version="x", account=acc)


@pytest.mark.django_db
def test_charge_uses_free_lot_first(chart):
    from api import ledger

    interp, lot = ledger.charge(chart.account, _make_interp(chart))
    chart.account.refresh_from_db()
    assert lot == "free"
    assert chart.account.free_balance == 0
    assert chart.account.credit_txns.filter(kind="consumption", lot="free", amount=-1).count() == 1
    assert ledger.credits_available(chart.account) == 0


@pytest.mark.django_db
def test_charge_raises_when_no_balance(chart):
    from api import ledger
    from api.interpretation_service import QuotaExceeded

    ledger.charge(chart.account, _make_interp(chart))  # gasta la única free
    # segunda carta de la misma cuenta, sin balance
    from api.models import BirthData, Chart
    bd = BirthData.objects.create(date="2001-01-01", lat=0, lng=0, tz_name="UTC")
    ch2 = Chart.objects.create(birth_data=bd, data={}, engine_version="x", account=chart.account)
    with pytest.raises(QuotaExceeded):
        ledger.charge(chart.account, _make_interp(ch2))


@pytest.mark.django_db
def test_charge_uses_paid_when_free_exhausted(chart):
    from api import ledger
    ledger.grant_paid(chart.account, 2)
    ledger.charge(chart.account, _make_interp(chart))  # gasta free
    from api.models import BirthData, Chart
    bd = BirthData.objects.create(date="2002-01-01", lat=0, lng=0, tz_name="UTC")
    ch2 = Chart.objects.create(birth_data=bd, data={}, engine_version="x", account=chart.account)
    interp, lot = ledger.charge(chart.account, _make_interp(ch2))
    chart.account.refresh_from_db()
    assert lot == "paid"
    assert chart.account.paid_balance == 1


@pytest.mark.django_db
def test_grant_paid_records_ledger(chart):
    from api import ledger
    ledger.grant_paid(chart.account, 5, note="manual")
    chart.account.refresh_from_db()
    assert chart.account.paid_balance == 5
    assert chart.account.credit_txns.filter(kind="purchase", lot="paid", amount=5).count() == 1
