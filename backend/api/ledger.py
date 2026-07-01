"""Ledger de créditos: balance + débito atómico.

El débito corre dentro de transaction.atomic con select_for_update sobre la
Account para serializar consumos concurrentes de la misma cuenta (cierra el
doble gasto). Toda mutación de balance deja su CreditTransaction.
"""

from django.conf import settings
from django.db import IntegrityError, transaction

from api.exceptions import QuotaExceeded
from api.models import Account, CreditTransaction


def credits_available(account) -> int:
    return account.free_balance + account.paid_balance


def charge(account, build_interpretation):
    """Cobra 1 crédito (free primero, luego paid) y crea la interpretación.

    build_interpretation: callable sin args que crea y devuelve la Interpretation.
    Devuelve (interpretation, lot). Lanza QuotaExceeded si no hay balance.
    """
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        if acc.free_balance > 0:
            lot = "free"
            acc.free_balance -= 1
        elif acc.paid_balance > 0:
            lot = "paid"
            acc.paid_balance -= 1
        else:
            raise QuotaExceeded()
        acc.save(update_fields=["free_balance", "paid_balance"])
        interp = build_interpretation()
        CreditTransaction.objects.create(
            account=acc, kind="consumption", lot=lot, amount=-1, interpretation=interp,
        )
    account.free_balance = acc.free_balance
    account.paid_balance = acc.paid_balance
    return interp, lot


def grant_paid(account, n: int, note: str = "") -> None:
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        acc.paid_balance += n
        acc.save(update_fields=["paid_balance"])
        CreditTransaction.objects.create(
            account=acc, kind="purchase", lot="paid", amount=n, note=note,
        )
    account.paid_balance = acc.paid_balance


def refund_credits(account, n: int, external_id: str, note: str = "") -> bool:
    """Revierte n créditos (clawback; saldo puede quedar negativo) de forma
    idempotente. Incrementa refund_count y marca la cuenta al cruzar el umbral.
    Devuelve True si aplicó, False si ya estaba procesado."""
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        try:
            with transaction.atomic():
                CreditTransaction.objects.create(
                    account=acc, kind="refund", lot="paid",
                    amount=-n, external_id=external_id, note=note,
                )
        except IntegrityError:
            # Solo es duplicado si esa external_id ya existe; cualquier otro
            # IntegrityError se propaga (no perder un crédito por un error real).
            if CreditTransaction.objects.filter(external_id=external_id).exists():
                return False
            raise
        acc.paid_balance -= n
        acc.refund_count += 1
        if acc.refund_count >= settings.REFUND_FLAG_THRESHOLD:
            acc.flagged = True
        acc.save(update_fields=["paid_balance", "refund_count", "flagged"])
    account.paid_balance = acc.paid_balance
    account.refund_count = acc.refund_count
    account.flagged = acc.flagged
    return True


def credit_purchase(account, n: int, external_id: str, note: str = "") -> bool:
    """Acredita n créditos pagos de forma idempotente por external_id.
    Devuelve True si acreditó, False si ya estaba procesado."""
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        try:
            with transaction.atomic():
                CreditTransaction.objects.create(
                    account=acc, kind="purchase", lot="paid",
                    amount=n, external_id=external_id, note=note,
                )
        except IntegrityError:
            # Solo es duplicado si esa external_id ya existe; cualquier otro
            # IntegrityError se propaga (no perder un crédito por un error real).
            if CreditTransaction.objects.filter(external_id=external_id).exists():
                return False
            raise
        acc.paid_balance += n
        acc.save(update_fields=["paid_balance"])
    account.paid_balance = acc.paid_balance
    return True
