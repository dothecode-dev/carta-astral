"""«Pagar es entrar» (spec docs/2026-10-07-spec-pagar-es-entrar.md).

Los momentos de una compra sin cuenta, en un solo módulo para que la regla
de seguridad viva en un lugar: nunca se abre sesión en una cuenta que existía
antes de la compra, y el checkout_id solo nunca alcanza para entrar.
"""

import logging
import secrets

from django.db import IntegrityError, transaction

from api import cupones, stripe_client
from api.accounts import resolver_cuenta
from api.chart_service import create_chart
from api.identity import hash_token, normalizar, tombstone_hmac_configurada
from api.models import Account, Chart, PasarelaCheckout, ProviderIdentity, Sujeto
from api.sso import VerifiedIdentity

logger = logging.getLogger(__name__)
PRODUCTO = "informe_natal"


class CuponNoAdmitido(Exception):
    """Un cupón del 100 % se canjea sin Stripe: sin cuenta no hay a quién dárselo."""


class NoDisponible(Exception):
    """Falta configuración que el webhook va a necesitar: mejor no cobrar."""


def comprobar_disponible() -> None:
    """Primer chequeo de toda apertura: la vista lo corre ANTES de validar
    nada, para que el 503 le gane al 400 (RF4)."""
    if not tombstone_hmac_configurada():
        raise NoDisponible("TOMBSTONE_HMAC_KEY")


def abrir(datos: dict, locale: str, codigo_cupon: str | None):
    """Crea la carta sin dueño, abre la sesión de Stripe y guarda la fila.

    Devuelve `(fila, nonce_en_claro)`; en la base sólo queda el hash del nonce.
    `datos` ya viene validado por la vista. La carta y la llamada a Stripe van
    en el mismo átomo para que un fallo de Stripe no deje una carta sin dueño;
    una sesión de Stripe huérfana (si la base falla después) vence sola a la hora.
    """
    comprobar_disponible()
    cupon = None
    if codigo_cupon:
        cupon = cupones.validar(codigo_cupon, PRODUCTO, account=None)
        if cupon.porcentaje >= 100:
            raise CuponNoAdmitido
    nonce = secrets.token_urlsafe(32)
    with transaction.atomic():
        carta = create_chart(datos, account=None)
        checkout_id, url = stripe_client.crear_checkout(
            None, PRODUCTO, chart=carta, locale=locale, cupon=cupon, terminos=True,
        )
        precio, descuento = cupones.precio_y_descuento(PRODUCTO, cupon)
        fila = PasarelaCheckout.objects.create(
            checkout_id=checkout_id, account=None, codigo_producto=PRODUCTO, chart=carta,
            locale=locale, cupon=cupon, descuento_centavos=descuento, url=url,
            precio_centavos=precio, anonimo=True, nonce_hash=hash_token(nonce),
        )
    return fila, nonce


def enmascarar(email: str) -> str:
    """`n***@mail.com`: lo justo para reconocerlo en un log sin guardarlo entero."""
    local, _, dominio = email.partition("@")
    return f"{local[:1]}***@{dominio}" if dominio else "***"


def _asegurar_identidad_email(cuenta: Account, email: str) -> None:
    """Que el login por código con este mail caiga en `cuenta` (RF12/RF17).

    `resolve_account` sólo enlaza por mail cuentas VERIFICADAS: una cuenta
    sin verificar y sin identidad `(email, mail)` quedaría fuera del login por
    código, que crearía otra cuenta y dejaría la compra invisible para quien
    pagó. Se agrega la identidad sin tocar `email_verified` ni `cuenta_nueva`:
    entrar sigue exigiendo el código del mail, nunca el pago.

    Si la identidad ya es de OTRA cuenta no se mueve nada —el login por código
    ya va a esa otra, y reasignarla sería quitarle la puerta a alguien—: queda
    a la vista para resolverlo a mano.
    """
    identidad = ProviderIdentity.objects.filter(provider="email", sub=email).first()
    if identidad is None:
        try:
            with transaction.atomic():
                ProviderIdentity.objects.create(provider="email", sub=email, account=cuenta)
            return
        except IntegrityError:  # carrera: la identidad se creó en paralelo
            identidad = ProviderIdentity.objects.get(provider="email", sub=email)
    if identidad.account_id != cuenta.pk:
        logger.warning(
            "compra anónima con mail %s: la cuenta %s lo tiene como email pero la "
            "identidad de login es de la cuenta %s; no se toca, revisar a mano",
            enmascarar(email), cuenta.pk, identidad.account_id,
        )


def adjudicar(checkout_id: str, email: str) -> Account | None:
    """La cuenta de una compra anónima pagada, por el mail del pago (RF5).

    Con `select_for_update` sobre la fila: dos entregas del mismo evento (o
    `completed` + `async_payment_succeeded`) se serializan acá y la segunda
    encuentra la cuenta ya puesta. Un mail existente —verificado o no— es
    esa cuenta y NUNCA se marca `cuenta_nueva`: es lo que impide entrar a una
    cuenta ajena pagando con su mail (RF11).

    `cuenta_nueva` sale de quien CREÓ la cuenta (`resolver_cuenta`), no de que
    el lookup por mail no haya encontrado nada: una `ProviderIdentity(email,
    sub)` previa de una cuenta con otro mail, o dos compras distintas con el
    mismo mail nuevo a la vez (cada una con el lock de SU fila; la carrera la
    decide la unicidad de la identidad), devuelven una cuenta que esta compra
    no creó.

    `None` si la fila no existe o no es anónima. Idempotente: si la fila ya
    tiene cuenta, la devuelve sin tocar nada.
    """
    email = normalizar(email)
    with transaction.atomic():
        fila = PasarelaCheckout.objects.select_for_update().filter(checkout_id=checkout_id).first()
        if fila is None or not fila.anonimo:
            return None
        if fila.account_id is not None:
            return fila.account
        # La más antigua si hay varias (cuentas duplicadas de antes de C3).
        existente = Account.objects.filter(email__iexact=email).order_by("pk").first()
        if existente is not None:
            cuenta, nueva = existente, False
            _asegurar_identidad_email(cuenta, email)
        else:
            # El mismo camino que el alta por mail de hoy: identidad
            # `(email, <mail normalizado>)` y regalo de bienvenida descontado
            # por el tombstone. Sin verificar: nadie probó todavía que el mail
            # sea de quien pagó; lo verifica entrar con el código (RF12).
            cuenta, nueva = resolver_cuenta(VerifiedIdentity(
                provider="email", sub=email, email=email, email_verified=False,
            ))
        fila.account, fila.cuenta_nueva = cuenta, nueva
        fila.save(update_fields=["account", "cuenta_nueva"])
        if fila.chart_id is not None:
            Chart.objects.filter(pk=fila.chart_id, account__isnull=True).update(account=cuenta)
            Sujeto.objects.filter(
                natal_de_id=fila.chart_id, account__isnull=True,
            ).update(account=cuenta)
    logger.info(
        "compra anónima %s adjudicada a la cuenta %s (nueva=%s, mail=%s)",
        checkout_id, cuenta.pk, nueva, enmascarar(email),
    )
    return cuenta
