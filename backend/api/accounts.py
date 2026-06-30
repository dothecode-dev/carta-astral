"""Find-or-create de Account a partir de una identidad SSO verificada.

Reglas (RF10): (1) si ya existe ProviderIdentity(provider, sub) -> esa cuenta;
(2) si el email viene verificado y matchea exactamente una cuenta verificada ->
linkear el sub a esa cuenta; (3) si no, crear cuenta nueva descontando el
free-tier ya consumido segun el tombstone del sub.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from api.identity import sub_hash
from api.models import Account, CreditTransaction, ProviderIdentity, SubTombstone
from api.sso import VerifiedIdentity

logger = logging.getLogger(__name__)


def resolve_account(vid: VerifiedIdentity) -> Account:
    existing = ProviderIdentity.objects.filter(provider=vid.provider, sub=vid.sub).first()
    if existing is not None:
        return existing.account

    if vid.email and vid.email_verified:
        matches = Account.objects.filter(email=vid.email, email_verified=True)
        if matches.count() == 1:
            account = matches.first()
            try:
                ProviderIdentity.objects.create(
                    provider=vid.provider, sub=vid.sub, account=account,
                )
            except IntegrityError:  # carrera: el sub se creo en paralelo
                logger.info("race linking %s sub to account; re-reading", vid.provider)
                return ProviderIdentity.objects.get(
                    provider=vid.provider, sub=vid.sub,
                ).account
            return account

    return _create_account(vid)


def _create_account(vid: VerifiedIdentity) -> Account:
    tomb = SubTombstone.objects.filter(sub_hash=sub_hash(vid.provider, vid.sub)).first()
    consumed = tomb.free_credits_consumed if tomb else 0
    free = max(0, settings.INSTALL_FREE_CREDITS - consumed)
    try:
        # El INSERT de ProviderIdentity puede colisionar con un login paralelo
        # del mismo sub. Atomic = si colisiona, se revierte la Account recien
        # creada. Capturamos el IntegrityError FUERA del bloque atomic: una vez
        # que el atomic sale por excepcion la transaccion se rollbackea limpia y
        # la conexion vuelve a ser usable para re-leer la identidad ganadora.
        # (capturar adentro y consultar ahi rompe con TransactionManagementError).
        with transaction.atomic():
            account = Account.objects.create(
                email=vid.email or "", email_verified=vid.email_verified,
                free_balance=free, paid_balance=0,
            )
            ProviderIdentity.objects.create(
                provider=vid.provider, sub=vid.sub, account=account,
            )
            if free > 0:
                CreditTransaction.objects.create(
                    account=account, kind="free_grant", lot="free", amount=free,
                )
    except IntegrityError:  # carrera: el sub se creo en paralelo
        logger.info("race creating %s sub; re-reading existing account", vid.provider)
        return ProviderIdentity.objects.get(
            provider=vid.provider, sub=vid.sub,
        ).account
    return account
