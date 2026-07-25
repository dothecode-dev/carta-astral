"""Borrado de cuenta: tombstone del free-tier consumido + borrado duro de
datos personales. El ledger (CreditTransaction) se conserva con account=NULL."""

import logging

from django.conf import settings
from django.db import transaction

from api import apple
from api.identity import sub_hash
from api.models import BirthData, SubTombstone

logger = logging.getLogger(__name__)


def delete_charts(account) -> None:
    """Borra todas las cartas de la cuenta y sus datos de nacimiento.

    Las interpretations cascadean con la carta. BirthData no cascadea solo
    (el FK va de Chart a BirthData), así que se barren los que quedan sin
    ninguna carta: contienen nombre, fecha y coordenadas de nacimiento.
    """
    with transaction.atomic():
        birth_ids = list(account.charts.values_list("birth_data_id", flat=True))
        account.charts.all().delete()
        BirthData.objects.filter(id__in=birth_ids, charts__isnull=True).delete()


def _revoke_apple(tokens) -> None:
    """Revoca en Apple los tokens de la cuenta ya borrada (guideline 5.1.1(v)).

    Best-effort a propósito: el borrado de datos ya ocurrió y no se deshace
    porque Apple esté caído. Lo que falla queda logueado como error.
    """
    if not tokens:
        return
    if not apple.is_configured():
        logger.error(
            "apple revoke omitido: faltan credenciales del server API (%d token/s pendientes)",
            len(tokens),
        )
        return
    for token in tokens:
        try:
            apple.revoke(token)
        except Exception as exc:  # AppleError / AppleNotConfigured
            logger.error("apple revoke falló para un token de cuenta borrada: %s", exc)


def delete_account(account) -> None:
    # Se leen ANTES del borrado; la llamada de red va DESPUÉS del commit, nunca
    # dentro del atomic (mantendría el lock de la fila durante el timeout de Apple).
    apple_tokens = list(
        account.identities.filter(provider="apple")
        .exclude(refresh_token="")
        .values_list("refresh_token", flat=True)
    )
    with transaction.atomic():
        consumed = max(
            0,
            min(settings.INSTALL_FREE_CREDITS, settings.INSTALL_FREE_CREDITS - account.free_balance),
        )
        for ident in account.identities.all():
            SubTombstone.objects.update_or_create(
                sub_hash=sub_hash(ident.provider, ident.sub),
                defaults={"free_credits_consumed": consumed},
            )
        delete_charts(account)
        account.sessions.all().delete()
        account.devices.update(account=None)
        account.identities.all().delete()
        account.delete()  # CreditTransaction.account -> SET_NULL (ledger preservado)
    _revoke_apple(apple_tokens)
