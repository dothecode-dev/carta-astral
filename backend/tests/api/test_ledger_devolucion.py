import pytest

from api import ledger
from api.models import CreditTransaction

pytestmark = pytest.mark.django_db


def test_devolver_repone_el_saldo(account):
    account.paid_balance = 0
    account.save()
    ledger.devolver(account, 1, note="informe fallido")
    account.refresh_from_db()
    assert account.paid_balance == 1


def test_devolver_no_marca_la_cuenta_como_sospechosa(account):
    # Un fallo técnico nuestro no es un reembolso: el usuario no hizo nada.
    antes = account.refund_count
    ledger.devolver(account, 1)
    account.refresh_from_db()
    assert account.refund_count == antes
    assert account.flagged is False


def test_devolver_deja_su_registro_en_el_ledger(account):
    ledger.devolver(account, 1, note="informe fallido")
    txn = CreditTransaction.objects.filter(account=account, kind="adjustment").last()
    assert txn.amount == 1
    assert txn.note == "informe fallido"
