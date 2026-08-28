import pytest
from django.conf import settings

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


def test_devolver_es_idempotente_por_external_id(account):
    # El hilo de la Tarea 10 puede sobrevivir a su propio lock y reintentar:
    # la segunda llamada con el mismo external_id no debe acreditar de nuevo.
    primera = ledger.devolver(account, 1, external_id="informe:123:fallo")
    segunda = ledger.devolver(account, 1, external_id="informe:123:fallo")
    account.refresh_from_db()
    assert primera is True
    assert segunda is False
    assert account.paid_balance == 1


def test_devolver_con_external_id_distinto_acredita_dos_veces(account):
    ledger.devolver(account, 1, external_id="informe:123:fallo")
    ledger.devolver(account, 1, external_id="informe:456:fallo")
    account.refresh_from_db()
    assert account.paid_balance == 2


def test_devolver_repone_al_lote_free_cuando_se_indica(account):
    # BUG 2: `devolver` fijaba `lot="paid"` siempre. Quien cobró de
    # `free_balance` tiene que poder pedir que la devolución vuelva ahí.
    account.free_balance = 0
    account.paid_balance = 5
    account.save()
    ledger.devolver(account, 1, lot="free")
    account.refresh_from_db()
    assert account.free_balance == 1
    assert account.paid_balance == 5


def test_devolver_repetido_nunca_marca_la_cuenta(account):
    # A diferencia de refund_credits, ninguna cantidad de llamadas a devolver()
    # debe cruzar REFUND_FLAG_THRESHOLD ni tocar refund_count: el usuario no
    # hizo nada, así que no hay umbral de sospecha que aplicarle.
    for i in range(settings.REFUND_FLAG_THRESHOLD + 2):
        ledger.devolver(account, 1, external_id=f"informe:{i}:fallo")
    account.refresh_from_db()
    assert account.refund_count == 0
    assert account.flagged is False
