"""Borrado de cuenta: tombstone del free-tier consumido + borrado duro de
datos personales. El ledger (CreditTransaction) se conserva con account=NULL."""

from django.conf import settings
from django.db import transaction

from api.identity import sub_hash
from api.models import BirthData, SubTombstone


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


def delete_account(account) -> None:
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
