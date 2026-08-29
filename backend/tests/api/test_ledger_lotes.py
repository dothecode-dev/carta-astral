"""El lote entra a `charge()` como parámetro, no lo elige la función.

Con dos productos (lectura breve = free, informe completo = paid) el lote
ES el producto: caer al otro lote cuando el pedido no tiene saldo cobraría
el producto equivocado (por ejemplo, un crédito de US$ 29 por una lectura
que el usuario pidió gratis). Estos tests cubren el comportamiento desde
los dos lados: sin free no cae al paid, sin paid no cae al free.
"""

import pytest

from api import ledger
from api.exceptions import QuotaExceeded
from api.models import Account, CreditTransaction

pytestmark = pytest.mark.django_db


def _acc(free=0, paid=0):
    return Account.objects.create(free_balance=free, paid_balance=paid)


def test_la_breve_gasta_free_aunque_haya_pagos():
    """Un crédito de US$ 29 no se gasta nunca en una lectura breve."""
    acc = _acc(free=2, paid=1)
    _, lot = ledger.charge(acc, lambda: None, lot="free")
    assert lot == "free"
    acc.refresh_from_db()
    assert (acc.free_balance, acc.paid_balance) == (1, 1)


def test_el_completo_gasta_paid_aunque_haya_free():
    """El informe completo nunca se paga con un crédito gratis, aunque sobre saldo free."""
    acc = _acc(free=2, paid=1)
    _, lot = ledger.charge(acc, lambda: None, lot="paid")
    assert lot == "paid"
    acc.refresh_from_db()
    assert (acc.free_balance, acc.paid_balance) == (2, 0)


def test_sin_free_no_cae_al_paid():
    """El fallback silencioso al otro lote es exactamente el bug que hay que
    evitar: cobraría US$ 29 por una lectura que el usuario pidió gratis."""
    acc = _acc(free=0, paid=3)
    with pytest.raises(QuotaExceeded):
        ledger.charge(acc, lambda: None, lot="free")
    acc.refresh_from_db()
    assert acc.paid_balance == 3
    assert CreditTransaction.objects.count() == 0


def test_sin_paid_no_cae_al_free():
    """Contrapunto: sin saldo pago, pedir el informe completo no se cobra
    silenciosamente con un crédito gratis."""
    acc = _acc(free=3, paid=0)
    with pytest.raises(QuotaExceeded):
        ledger.charge(acc, lambda: None, lot="paid")
    acc.refresh_from_db()
    assert acc.free_balance == 3
