"""Find-or-create de Account a partir de una identidad SSO verificada.

Reglas (RF10): (1) si ya existe ProviderIdentity(provider, sub) -> esa cuenta;
(2) si el email viene verificado y matchea (sin distinguir mayúsculas: C3,
revisión de `puertas-de-acceso`) una o más cuentas verificadas -> linkear el
sub a la más antigua de ellas; (3) si no matchea ninguna, crear cuenta nueva
descontando el free-tier ya consumido segun el tombstone del sub.

Entre (2) y (3), una excepción acotada («pagar es entrar», revisión final):
con el mail verificado por el proveedor y sin cuenta verificada que lo tenga,
se enlaza la cuenta SIN verificar que creó una compra sin cuenta con ese mail
(`_cuenta_de_compra`), y entrar así la verifica y cierra sus otras sesiones
(`probar_mail`, el mismo criterio que el login por código, RF17).

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
from api.models import Account, PasarelaCheckout, ProviderIdentity, Session, SubTombstone
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


def probar_mail(account: Account) -> None:
    """Alguien acaba de probar que el mail de una cuenta sin verificar es suyo
    (RF17): la cuenta queda verificada y se cierran TODAS sus sesiones.

    La cuenta la creó una compra sin cuenta con un mail que nadie había
    probado, y quien pagó pudo usar el mail de otra persona: su navegador
    entró por el nonce. Cuando la dueña real del mail aparece —con el código
    o con un proveedor que verificó el mail—, el pagador no puede seguir
    viendo los datos de ella. Quien llama crea la sesión nueva DESPUÉS, así
    que «todas» son las demás.

    Lo comparten el login por código (`sessions.py`) y el enlace por
    proveedor (`_enlazar_cuenta_de_compra`): si el criterio cambia, cambia
    para las dos puertas.
    """
    account.email_verified = True
    account.save(update_fields=["email_verified"])
    Session.objects.filter(account=account).delete()


def _cuenta_de_compra(email: str) -> Account | None:
    """La cuenta sin verificar que nació de una compra sin cuenta con este
    mail, si existe. Tiene que cumplir TODO:

    - `email` igual (sin distinguir mayúsculas) y `email_verified=False`;
    - es la dueña de la identidad `(email, <mail normalizado>)`: la puerta por
      la que entra el código de ese mail;
    - un checkout anónimo la CREÓ (`anonimo=True, cuenta_nueva=True`).

    Por la unicidad de la identidad hay a lo sumo una. Cualquier otra cuenta
    sin verificar sigue sin enlazarse: puede ser la de alguien que entró con
    Google usando un mail ajeno sin verificar (pre-account-hijacking).
    """
    return (
        Account.objects.filter(
            email__iexact=email, email_verified=False,
            identities__provider="email", identities__sub=email,
        )
        .filter(pk__in=PasarelaCheckout.objects.filter(
            anonimo=True, cuenta_nueva=True,
        ).values("account_id"))
        .order_by("pk").first()
    )


def _enlazar_cuenta_de_compra(vid: VerifiedIdentity, cuenta: Account) -> Account:
    """Enlaza el sub del proveedor a la cuenta que creó una compra, la
    verifica y cierra sus otras sesiones, en una sola transacción.

    La cuenta se relee con `select_for_update`: el canje del nonce
    (`compra_anonima._cuenta_nueva_sin_verificar`) la lockea para decidir si
    abre sesión, así que o el canje termina antes (y su sesión cae acá) o
    espera y la ve verificada. Si el sub se enlazó en paralelo, se devuelve
    la cuenta ganadora sin tocar nada más.
    """
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=cuenta.pk)
        try:
            with transaction.atomic():
                ProviderIdentity.objects.create(provider=vid.provider, sub=vid.sub, account=acc)
        except IntegrityError:  # carrera: el sub se creó en paralelo
            logger.info("race linking %s sub to purchase account; re-reading", vid.provider)
            return ProviderIdentity.objects.get(provider=vid.provider, sub=vid.sub).account
        if not acc.email_verified:
            probar_mail(acc)
    logger.info(
        "%s enlazado a la cuenta %s, creada por una compra sin cuenta: verificada",
        vid.provider, acc.pk,
    )
    return acc


def resolve_account(vid: VerifiedIdentity) -> Account:
    return resolver_cuenta(vid)[0]


def resolver_cuenta(vid: VerifiedIdentity) -> tuple[Account, bool]:
    """`resolve_account`, diciendo además si la cuenta la creó ESTA llamada.

    Lo necesita la compra anónima (spec «pagar es entrar», RF5/RF11): sólo una
    cuenta creada por la compra deja entrar al navegador que pagó. Que no la
    haya encontrado un lookup previo no alcanza para decirlo —la identidad
    puede existir ya, o crearse en paralelo y ganar la carrera del `INSERT`—:
    el único que sabe si creó es el que creó.
    """
    existing = ProviderIdentity.objects.filter(provider=vid.provider, sub=vid.sub).first()
    if existing is not None:
        return existing.account, False

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
                ).account, False
            return account, False

        # Sólo si no hay una verificada (que manda, arriba) y sólo con el mail
        # verificado por el proveedor: con `email_verified=False` esto nunca
        # corre.
        de_compra = _cuenta_de_compra(normalizado)
        if de_compra is not None:
            return _enlazar_cuenta_de_compra(vid, de_compra), False

    return _create_account(vid)


def _create_account(vid: VerifiedIdentity) -> tuple[Account, bool]:
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
        ).account, False
    return account, True
