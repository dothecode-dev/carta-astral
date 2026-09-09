"""Find-or-create de Account a partir de una identidad SSO verificada.

Reglas (RF10): (1) si ya existe ProviderIdentity(provider, sub) -> esa cuenta;
(2) si el email viene verificado y matchea (sin distinguir mayúsculas: C3,
revisión de `puertas-de-acceso`) una o más cuentas verificadas -> linkear el
sub a la más antigua de ellas; (3) si no matchea ninguna, crear cuenta nueva
descontando el free-tier ya consumido segun el tombstone del sub.

El match es case-insensitive porque el email no llega normalizado desde el
mismo lugar en las tres puertas: `codigos_acceso.py` lo normaliza al guardar
el `CodigoAcceso`, pero un `id_token` de Google o Apple trae el casing que el
proveedor le dio al alta (gmail.com normaliza a minúsculas; un dominio
Workspace no). Sin esto, la misma persona podía terminar con una cuenta por
cada casing con el que un proveedor mandó su dirección — cada una con su
propio regalo de bienvenida y sus propias compras.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction

from api.canje import otorgar
from api.identity import normalizar, sub_hash
from api.models import Account, ProviderIdentity, SubTombstone
from api.sso import VerifiedIdentity

logger = logging.getLogger(__name__)


def otorgar_bienvenida(account, cantidad: int) -> None:
    """Las lecturas breves de regalo, una sola vez por cuenta.

    `cantidad` ya viene descontada por el tombstone del sub (RF10): quien
    llama es responsable de pasar lo que falta, no `INSTALL_FREE_CREDITS` a
    secas, o borrar la cuenta y volver a entrar regalaría lecturas sin límite.
    Si no queda nada por regalar, no se crea ni derecho ni movimiento: cero
    no es un regalo.

    El external_id determinístico es lo que hace idempotente al regalo: un
    reintento del SSO que vuelva a llamar acá no puede regalar el doble.
    """
    if cantidad <= 0:
        return
    otorgar(
        account, "lectura_breve", cantidad,
        origen="regalo", external_id=f"bienvenida:{account.pk}",
        note="regalo de bienvenida",
    )


def resolve_account(vid: VerifiedIdentity) -> Account:
    existing = ProviderIdentity.objects.filter(provider=vid.provider, sub=vid.sub).first()
    if existing is not None:
        return existing.account

    if vid.email and vid.email_verified:
        normalizado = normalizar(vid.email)
        # `iexact` y no `email=normalizado`: matchea también las cuentas que ya
        # están guardadas con casing mixto (C3, revisión de `puertas-de-acceso`)
        # sin depender de una migración que las toque a todas una por una.
        matches = list(
            Account.objects.filter(email__iexact=normalizado, email_verified=True)
            .order_by("pk")
        )
        if matches:
            if len(matches) > 1:
                # No debería pasar: una dirección verificada, en teoría, es una
                # sola cuenta. Si pasa, es que ya existían duplicadas de antes
                # de este fix (C3) o de una carrera. Se linkea a la más
                # antigua en vez de sumar una cuenta más, y se deja rastro para
                # que alguien las revise a mano — mezclar los datos de las dos
                # (cartas, derechos, compras) no es una decisión que este
                # código pueda tomar solo. Nunca la dirección completa en el
                # log, sólo los pks.
                logger.warning(
                    "email verificado con %d cuentas duplicadas (pks=%s); "
                    "se linkea %s a la más antigua",
                    len(matches), [a.pk for a in matches], vid.provider,
                )
            account = matches[0]
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
                # Normalizada para que el matcheo por `email` (arriba) siga
                # encontrándola sin depender de `iexact` en el futuro, y para
                # que dos cuentas nuevas con la misma dirección en casing
                # distinto no puedan crearse en paralelo sin que se note.
                email=normalizar(vid.email) if vid.email else "",
                email_verified=vid.email_verified,
            )
            ProviderIdentity.objects.create(
                provider=vid.provider, sub=vid.sub, account=account,
            )
            # El regalo de bienvenida se registra UNA sola vez, como
            # `Movimiento` (Task 10). La `CreditTransaction` de `free_grant`
            # que había acá era el mismo hecho anotado por segunda vez en el
            # libro del modelo viejo, que quedó congelado y sin escritores.
            otorgar_bienvenida(account, free)
    except IntegrityError:  # carrera: el sub se creo en paralelo
        logger.info("race creating %s sub; re-reading existing account", vid.provider)
        return ProviderIdentity.objects.get(
            provider=vid.provider, sub=vid.sub,
        ).account
    return account
