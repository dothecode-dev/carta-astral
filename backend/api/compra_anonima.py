"""«Pagar es entrar» (spec docs/2026-10-07-spec-pagar-es-entrar.md).

Los momentos de una compra sin cuenta, en un solo módulo para que la regla
de seguridad viva en un lugar: nunca se abre sesión en una cuenta que existía
antes de la compra, y el checkout_id solo nunca alcanza para entrar.
"""

import logging
import secrets

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from api import codigos_acceso, cupones, notificaciones, stripe_client
from api.accounts import resolver_cuenta
from api.auth import create_session
from api.chart_service import create_chart
from api.identity import hash_token, normalizar, tombstone_hmac_configurada
from api.models import Account, BirthData, Chart, CodigoAcceso, PasarelaCheckout, ProviderIdentity, Sujeto
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

    Sólo para una cuenta con el mail VERIFICADO (ver `adjudicar`: a una sin
    verificar nunca se le agrega). No toca `email_verified` ni `cuenta_nueva`:
    entrar sigue exigiendo el código del mail, nunca el pago.

    Si entre el lookup y el `INSERT` la identidad se creó para OTRA cuenta
    (carrera con un login por código en paralelo) no se mueve nada —el login
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

    Sólo se confía en mails PROBADOS. Con el mail normalizado, en este orden:

    1. `ProviderIdentity(email, mail)` → esa cuenta. Es la puerta por la que
       entra quien prueba el mail con el código, así que la compra va donde
       esa persona la va a ver.
    2. Una cuenta con `email__iexact=mail` y `email_verified=True` (la más
       antigua) → esa cuenta, y se le agrega la identidad email para que el
       login por código caiga ahí (sin ella `resolve_account` sí la enlazaría,
       pero queda explícito y no depende de esa regla).
    3. Si no → cuenta nueva por `resolver_cuenta`, el mismo camino que el alta
       por mail de hoy (regalo de bienvenida descontado por el tombstone).

    Una cuenta con el mail SIN verificar y sin identidad email nunca recibe
    nada: es pre-account-hijacking. Alguien puede entrar con Google usando un
    mail ajeno que Google no verificó (`sso.py` lo acepta) y quedar con una
    cuenta a nombre de ese mail; si la compra de la dueña real —y su carta, y
    la identidad email— fueran ahí, al entrar por código caería en la cuenta
    del atacante. Se crea otra cuenta aunque ya exista una con el mismo mail
    sin verificar (`Account.email` no es único).

    Ninguna cuenta encontrada (1 y 2) se marca `cuenta_nueva`: pagar con el
    mail de otro no abre sesión en su cuenta (RF11). Y `cuenta_nueva` sale de
    quien CREÓ la cuenta (`resolver_cuenta`), no de que los lookups no hayan
    encontrado nada: dos compras distintas con el mismo mail nuevo a la vez
    (cada una con el lock de SU fila; la carrera la decide la unicidad de la
    identidad) devuelven, a la que pierde, una cuenta que no creó.

    Con `select_for_update` sobre la fila: dos entregas del mismo evento (o
    `completed` + `async_payment_succeeded`) se serializan acá y la segunda
    encuentra la cuenta ya puesta. `None` si la fila no existe o no es
    anónima. Idempotente: si la fila ya tiene cuenta, la devuelve sin tocar
    nada.
    """
    email = normalizar(email)
    with transaction.atomic():
        fila = PasarelaCheckout.objects.select_for_update().filter(checkout_id=checkout_id).first()
        if fila is None or not fila.anonimo:
            return None
        if fila.account_id is not None:
            return fila.account
        identidad = (
            ProviderIdentity.objects.filter(provider="email", sub=email)
            .select_related("account").first()
        )
        # La más antigua si hay varias (cuentas duplicadas de antes de C3).
        # Sólo se consulta si la identidad no resolvió: es el paso 2.
        verificada = None if identidad is not None else (
            Account.objects.filter(email__iexact=email, email_verified=True)
            .order_by("pk").first()
        )
        if identidad is not None:
            cuenta, nueva = identidad.account, False
        elif verificada is not None:
            cuenta, nueva = verificada, False
            _asegurar_identidad_email(cuenta, email)
        else:
            # Identidad `(email, <mail normalizado>)` y cuenta sin verificar:
            # nadie probó todavía que el mail sea de quien pagó; lo verifica
            # entrar con el código (RF12).
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


def descartar(checkout_id: str) -> bool:
    """Borra lo que dejó una compra sin cuenta que nunca se pagó (RF8).

    Se llama cuando Stripe avisa que la sesión venció. Con `select_for_update`
    sobre la fila, para que `expired` y un `completed` que llega a la vez se
    serialicen: gana el que toma el lock primero. Si ya hay cuenta o plata
    acreditada —aunque el acreditado haya fallado y esté pendiente de
    reintento— no se borra nada: la carta es de alguien.

    Borra la carta (su sujeto natal cae por CASCADE) y el `BirthData` si
    ninguna otra carta lo usa. La fila queda como registro, sin carta.
    `True` si descartó algo. Sólo se loguea el checkout, nunca datos de
    nacimiento.
    """
    with transaction.atomic():
        fila = PasarelaCheckout.objects.select_for_update().filter(checkout_id=checkout_id).first()
        if (
            fila is None or not fila.anonimo or fila.account_id is not None
            or fila.acreditado_at is not None or fila.chart_id is None
        ):
            return False
        carta_id = fila.chart_id
        birth_data_id = Chart.objects.values_list("birth_data_id", flat=True).get(pk=carta_id)
        fila.chart = None
        fila.sujeto = None
        fila.save(update_fields=["chart", "sujeto"])
        Chart.objects.filter(pk=carta_id).delete()
        if not Chart.objects.filter(birth_data_id=birth_data_id).exists():
            BirthData.objects.filter(pk=birth_data_id).delete()
    logger.info("compra anónima %s vencida sin pagar: carta descartada", checkout_id)
    return True


#: Vida del nonce, desde que se acreditó el pago. Es la vida máxima de la
#: cookie del nonce (spec RF2, ≤ 24 h): pasado eso nadie legítimo lo tiene,
#: así que el canje responde `invalido` en TODAS sus ramas —ni sesión ni
#: código—. Si no, quien guardó el nonce aparte podría seguir disparando
#: mails de código a la dueña del mail para siempre.
VIDA_CANJE_POR_NONCE = timezone.timedelta(hours=24)

#: Un código sin usar para el mismo mail y destino creado hace menos que esto
#: alcanza: recargar /compra no manda otro mail.
CODIGO_RECIENTE = timezone.timedelta(minutes=10)


def _cuenta_nueva_sin_verificar(fila: PasarelaCheckout) -> Account | None:
    """La cuenta creada por la compra, lockeada, si el nonce todavía puede
    abrir sesión en ella; `None` si no.

    No alcanza con `cuenta_nueva` (que dice quién creó la cuenta, no qué es
    hoy). Canje tardío: alguien paga con el mail de otra persona que no tenía
    cuenta y no canjea; la dueña del mail entra con código (RF17: la cuenta
    se verifica y se cierran las demás sesiones); si después el nonce del
    pagador abriera sesión, se llevaría un token de la cuenta de ella. Con el
    mail ya verificado, el canje cae a la rama del código.

    La cuenta se relee con `select_for_update`, no se usa la del
    `select_related`: el lock del canje es sobre la fila del checkout, y un
    login por código en paralelo puede verificar la cuenta y borrar sus
    sesiones entre esa lectura y el `create_session`. Con el lock, o el login
    termina antes (y acá se ve verificada) o espera a que el canje termine (y
    borra la sesión recién creada). Orden de locks: fila del checkout →
    cuenta, el mismo que el resto del módulo; ningún camino lockea la cuenta
    y después la fila.
    """
    cuenta = Account.objects.select_for_update().get(pk=fila.account_id)
    return None if cuenta.email_verified else cuenta


def _saldo_pendiente(fila: PasarelaCheckout) -> dict:
    """RF5b: si el pago saldó una deuda, la web no espera un informe."""
    return {"saldo_pendiente": True} if fila.saldo_deuda else {}


def _codigo_reciente(email: str, destino: str) -> bool:
    return CodigoAcceso.objects.filter(
        email=normalizar(email), destino=destino, usado_en__isnull=True,
        expira_en__gt=timezone.now(), creado_en__gte=timezone.now() - CODIGO_RECIENTE,
    ).exists()


def canjear(checkout_id: str, nonce: str) -> dict:
    """El navegador que pagó vuelve de Stripe (RF10-RF13).

    La sesión sólo se abre para una cuenta CREADA por esta compra
    (`cuenta_nueva`), con el nonce de ese navegador y una sola vez. El nonce
    se mira ANTES que todo lo demás: sin él, ni siquiera se revela si la
    compra está pendiente o es de un mail con cuenta. Toda falla es
    `invalido`, sin decir cuál.

    A un mail que ya tenía cuenta (`cuenta_nueva=False`) NUNCA se le abre
    sesión (RF11): se le manda el código de acceso con destino la carta
    (RF12). Tampoco a una cuenta nueva ya verificada
    (`_cuenta_nueva_sin_verificar`). Eso no se gasta —un segundo canje vuelve
    a dar `codigo`—, pero si ya hay un código reciente sin usar para ese mail
    y destino no se manda otro (dos canjes del mismo checkout se serializan
    en el lock de la fila, así que el segundo ve el código del primero), y el
    cupo por hora de `codigos_acceso.pedir` frena el resto. Pasadas
    `VIDA_CANJE_POR_NONCE` desde el pago, todo es `invalido`. El mail sale
    después del commit: el lock de la fila no espera a Resend.

    `select_for_update` sobre la fila: dos canjes simultáneos con el mismo
    nonce se serializan y el segundo ve `canjeado_at` puesto.
    """
    if not nonce:
        return {"estado": "invalido"}
    envio = None
    with transaction.atomic():
        # `of=("self",)`: Postgres no deja lockear el lado nullable de un
        # LEFT JOIN (cuenta y carta pueden faltar); el lock es de la fila.
        fila = (
            PasarelaCheckout.objects.select_for_update(of=("self",))
            .select_related("account", "chart").filter(checkout_id=checkout_id).first()
        )
        if (
            fila is None or not fila.anonimo or not fila.nonce_hash
            or not secrets.compare_digest(fila.nonce_hash, hash_token(nonce))
        ):
            return {"estado": "invalido"}
        if fila.acreditado_at is None or fila.account_id is None:
            return {"estado": "pendiente"}
        if timezone.now() - fila.acreditado_at > VIDA_CANJE_POR_NONCE:
            return {"estado": "invalido"}
        destino = (
            f"/{fila.locale}/carta/{fila.chart.uuid}" if fila.chart_id is not None
            else f"/{fila.locale}/cuenta"
        )
        if fila.cuenta_nueva and fila.canjeado_at is not None:
            return {"estado": "invalido"}
        cuenta = _cuenta_nueva_sin_verificar(fila) if fila.cuenta_nueva else None
        if cuenta is not None:
            fila.canjeado_at = timezone.now()
            fila.save(update_fields=["canjeado_at"])
            return {
                "estado": "sesion", "token": create_session(cuenta),
                "destino": destino, "account_id": cuenta.pk, **_saldo_pendiente(fila),
            }
        # Mail que ya tenía cuenta, o cuenta nueva que dejó de serlo (ver
        # `_cuenta_nueva_sin_verificar`): NUNCA sesión (RF11). Se le manda el código.
        #
        # Al mail de la CUENTA, no a uno guardado en la fila: por construcción
        # de `adjudicar` coinciden —la cuenta se eligió o se creó por el mail
        # del pago (identidad email, verificada con ese mail, o alta con él)—.
        # Si `Account.email` llegara a ser editable, eso deja de valer y hay
        # que guardar el mail del pago en la fila y mandar el código ahí.
        email = fila.account.email
        try:
            if not _codigo_reciente(email, destino):
                codigo, claro, _ = codigos_acceso.pedir(email, destino=destino)
                envio = (codigo, claro, fila.locale)
        except codigos_acceso.DemasiadosPedidos:
            logger.info(
                "compra anónima %s: %s ya pidió todos los códigos de la hora, no se reenvía",
                checkout_id, enmascarar(email),
            )
    if envio is not None:
        codigo, claro, lang = envio
        try:
            notificaciones.enviar_codigo(codigo.email, claro, lang)
        except notificaciones.EnvioFallido as exc:
            logger.error(
                "compra anónima %s: no se pudo enviar el código a %s: %s",
                checkout_id, enmascarar(codigo.email), exc,
            )
            # Mismo criterio que `PedirCodigoView` (Ruling 13): un mail que no
            # salió no cuenta para el cupo de la hora.
            CodigoAcceso.objects.filter(pk=codigo.pk).update(envios=F("envios") - 1)
    return {
        "estado": "codigo", "email": enmascarar(email), "destino": destino,
        **_saldo_pendiente(fila),
    }
