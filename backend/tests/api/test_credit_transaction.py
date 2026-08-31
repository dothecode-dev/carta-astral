"""`CreditTransaction`: el libro del modelo de cobro viejo, ya sin escritores.

La tabla queda congelada a propósito —es el registro histórico de lo que pasó
antes del modelo de canje y `SubTombstone` se apoya en esa historia—, así que
lo que se prueba acá es que las garantías del esquema siguen en pie. Los tests
de idempotencia venían de `test_ledger_iap.py`, que murió con `api/ledger.py`:
la restricción que los sostiene es de la BASE (un índice único PARCIAL), su
semántica difiere entre SQLite y Postgres, y perderla habría sido perder la
única verificación de que el índice existe de verdad en el motor real.
"""

import pytest
from django.db import IntegrityError



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


@pytest.mark.django_db
def test_external_id_es_unico_cuando_esta_presente():
    from api.models import Account, CreditTransaction

    acc = Account.objects.create()
    CreditTransaction.objects.create(
        account=acc, kind="purchase", lot="paid", amount=5, external_id="evt_1",
    )
    with pytest.raises(IntegrityError):
        CreditTransaction.objects.create(
            account=acc, kind="purchase", lot="paid", amount=5, external_id="evt_1",
        )


@pytest.mark.django_db
def test_el_external_id_vacio_no_dedupea():
    """El índice es PARCIAL (`condition=Q(external_id__gt="")`): las
    transacciones internas (consumos, regalos) no llevan external_id y no
    tienen que chocar entre sí."""
    from api.models import Account, CreditTransaction

    acc = Account.objects.create()
    CreditTransaction.objects.create(account=acc, kind="consumption", lot="free", amount=-1)
    CreditTransaction.objects.create(account=acc, kind="consumption", lot="free", amount=-1)
