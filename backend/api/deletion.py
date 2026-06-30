"""Borrado de cuenta: tombstone del free-tier consumido + borrado duro de
datos personales. El ledger (CreditTransaction) se conserva con account=NULL."""

from django.conf import settings
from django.db import transaction

from api.identity import sub_hash
from api.models import SubTombstone


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
        # charts CASCADE sus interpretations al borrarse
        account.charts.all().delete()
        account.sessions.all().delete()
        account.devices.update(account=None)
        account.identities.all().delete()
        account.delete()  # CreditTransaction.account -> SET_NULL (ledger preservado)
