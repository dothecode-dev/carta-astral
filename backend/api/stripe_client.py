"""Todo lo que habla con Stripe vive acá, y nada más lo importa.

La capa HTTP (`webhooks_stripe.py`, `checkout.py`) no conoce la librería: pide
por estas funciones. Así el día que Stripe cambie una firma de método, se toca
un archivo.
"""

import datetime as dt
import logging

import stripe
from django.conf import settings
from django.utils import timezone

from api.catalogo import producto

logger = logging.getLogger(__name__)


# Los idiomas que el sitio sirve, y que Stripe también soporta en su checkout.
# Lista blanca y no concatenación: el locale llega del navegador y termina en la
# URL a la que Stripe devuelve a la persona después de pagar.
LOCALES = ("es", "en", "pt")
LOCALE_POR_DEFECTO = "es"

# Cuánto vive una sesión de pago. Sin decirlo, Stripe la deja abierta 24 h, y
# durante todo ese tiempo la cuenta tendría que decir algo de un pago que
# nadie hizo. Una hora alcanza de sobra para pagar, y es lo que dura el link
# «retomar el pago» de la cuenta. Stripe admite entre 30 minutos y 24 horas.
# Al vencer manda `checkout.session.expired`; el endpoint del dashboard tiene
# que estar suscripto a ese evento (nada en el repo lo verifica).
VENCIMIENTO_SESION = dt.timedelta(hours=1)


class FirmaInvalida(Exception):
    """La entrega no viene de Stripe, o no viene entera."""


class StripeNoConfigurado(Exception):
    """Falta la clave, o el producto no tiene Product mapeado en Stripe."""


class StripeError(Exception):
    """Stripe respondió algo que no es una sesión.

    Propia y no `stripe.StripeError` a secas para que la vista pueda
    distinguirla y responder 502 sin dejar un `PasarelaCheckout` a medias.
    """


class CuponRechazado(StripeError):
    """Stripe no aceptó el promotion code al abrir la sesión: agotado, vencido
    o apagado allá. Medido el 06-09-2026 en sandbox: `InvalidRequestError`
    con `code="coupon_expired"` y `param="discounts[0][promotion_code][coupon]"`.
    Se distingue por el `param`, que es lo que dice QUÉ rechazó."""


def verificar_firma(cuerpo: bytes, cabecera: str, secreto: str) -> dict:
    """Devuelve el evento sólo si la firma y el timestamp son válidos.

    `cuerpo` son los BYTES exactos que llegaron (`request.body`), no el dict
    parseado: Stripe firma esos bytes y volver a serializar da otros. La
    verificación la hace la librería oficial —HMAC-SHA256 con comparación en
    tiempo constante y tolerancia de timestamp—, que es código de seguridad
    que no tiene sentido reescribir. Los tests firman a mano, con el algoritmo
    de la documentación pública, para que esto quede anclado a algo que no
    somos nosotros.
    """
    try:
        evento = stripe.Webhook.construct_event(cuerpo, cabecera, secreto)
    except (stripe.SignatureVerificationError, ValueError) as e:
        # El motivo, no sólo el rechazo: la librería distingue cuerpo ilegible,
        # header ausente, timestamp fuera de tolerancia y firma que no coincide,
        # y son problemas distintos con arreglos distintos. Son mensajes fijos
        # de la librería: no arrastran nada del payload.
        raise FirmaInvalida(str(e)) from e
    # `to_dict()` y no `dict(...)`: la librería devuelve un `Event`, que no es
    # un mapping y revienta con TypeError si se lo trata como tal. Lo que sale
    # de acá es un dict común —también en lo anidado— para que el resto del
    # código no tenga que saber de la librería.
    return evento.to_dict()


def obtener_sesion(session_id: str) -> dict:
    """La sesión tal como la ve Stripe, con los line items expandidos.

    El payload del evento sirve para saber QUÉ pasó; para saber cuánto y de qué
    producto se vuelve a preguntar, que es lo que Stripe recomienda: el evento
    puede llegar demorado o reordenado, y el estado bueno es el de la API. Si
    esta llamada falla, quien llama responde 5xx y Stripe reintenta.
    """
    stripe.api_key = settings.STRIPE_SECRET_KEY
    sesion = stripe.checkout.Session.retrieve(session_id, expand=["line_items"])
    return sesion.to_dict()


def sesion_por_payment_intent(payment_intent: str) -> dict | None:
    """La Checkout Session de ese PaymentIntent, o None. Para una disputa que
    llega antes de que la fila tenga el PI (EC16). Si la API falla, la
    excepción sube y el webhook pide el reintento."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    lista = stripe.checkout.Session.list(payment_intent=payment_intent, limit=1)
    return lista.data[0].to_dict() if lista.data else None


def product_de(codigo_producto: str) -> str:
    """El id del Product de Stripe para ese producto nuestro, de
    `STRIPE_PRODUCTOS`. Falla ANTES de abrir un pago que después nadie
    podría acreditar."""
    try:
        return settings.STRIPE_PRODUCTOS[codigo_producto]
    except KeyError:
        raise StripeNoConfigurado(f"{codigo_producto} no tiene Product en STRIPE_PRODUCTOS") from None


def codigo_de_product(product_id: str) -> str:
    """El código del catálogo para ese Product. `KeyError` si no lo mapeamos:
    acreditar un producto que no sabemos cuál es sería entregar cualquier
    cosa."""
    for codigo, prod in settings.STRIPE_PRODUCTOS.items():
        if prod == product_id:
            return codigo
    raise KeyError(product_id)


#: Cómo pide Stripe cada idioma nuestro. `pt` a secas es Portugal; la web y
#: Brasil hablan `pt-BR`.
_LOCALE_STRIPE = {"es": "es", "en": "en", "pt": "pt-BR"}

#: Cuánto vive un QR de Pix después de confirmado: lo mismo que la sesión. Sin
#: esto Stripe lo deja 4 horas (medido el 13-10-2026).
VENCIMIENTO_PIX = int(VENCIMIENTO_SESION.total_seconds())


#: Cómo se llama, en la URL de retorno, el parámetro con la sesión de Stripe.
#: Lo lee `web/app/[locale]/compra/page.tsx` para preguntar en qué quedó la
#: compra y mostrar el informe escribiéndose.
PARAM_RETORNO = "checkout_id"

#: El nombre que usa la documentación de Stripe en sus ejemplos, y por eso el
#: que termina copiado en la variable de entorno. La web lo acepta también.
PARAM_RETORNO_ALIAS = "session_id"


def _validar_success_url(url: str) -> None:
    """Que la URL de retorno traiga lo que la página de retorno va a buscar.

    Esto existe por un fallo del 04-09-2026, encontrado probando la compra
    entera en el staging: `STRIPE_SUCCESS_URL` decía
    `?session_id={CHECKOUT_SESSION_ID}` y la página lee `checkout_id`, así que
    quien terminaba de pagar caía en la pantalla genérica —"lo que compraste te
    espera en tu cuenta"— en vez de ver su informe escribiéndose. No rompía
    nada visible: la compra se acreditaba igual y el informe arrancaba igual.
    Sólo estaba mal la única pantalla que ve el que acaba de pagar.

    El acuerdo entre una variable de entorno y una página del otro proyecto no
    lo chequeaba nadie. Falla ACÁ, antes de abrir el pago, porque un error de
    configuración nuestro tiene que aparecer antes de cobrarle a alguien y no
    después.
    """
    if not url:
        raise StripeNoConfigurado("STRIPE_SUCCESS_URL no configurado")
    if "{CHECKOUT_SESSION_ID}" not in url:
        raise StripeNoConfigurado(
            "STRIPE_SUCCESS_URL no trae {CHECKOUT_SESSION_ID}: "
            "la página de retorno no puede saber qué compra mostrar",
        )
    if f"{PARAM_RETORNO}=" not in url and f"{PARAM_RETORNO_ALIAS}=" not in url:
        raise StripeNoConfigurado(
            f"STRIPE_SUCCESS_URL tiene que pasar la sesión como "
            f"`{PARAM_RETORNO}=` (o `{PARAM_RETORNO_ALIAS}=`): con otro nombre, "
            f"quien termina de pagar ve la pantalla genérica en vez de su compra",
        )


def crear_checkout(
    account, codigo_producto: str, sujeto=None, locale: str = LOCALE_POR_DEFECTO, cupon=None,
    terminos: bool = False, moneda: str = "usd",
) -> tuple[str, str]:
    """Abre una sesión de pago y devuelve `(session_id, url)`.

    `KeyError` si el producto no está en el catálogo o no se vende en `moneda`,
    `ValueError` si es gratis o está retirado, y `StripeNoConfigurado` si falta
    la clave o el Product: todos errores de configuración nuestra (o de un
    pedido mal armado), no de quien compra.

    El precio va en `price_data` —Product + moneda + monto del catálogo— y no
    como un Price id: MEDIDO el 13-10-2026 que Managed Payments lo acepta, que
    en `brl` ofrece Pix, y que `amount_subtotal` llega en centavos de real.

    Con `cupon`, la sesión lleva su Promotion Code en `discounts` y Stripe
    aplica el descuento y cuenta el uso al pagar. NUNCA `allow_promotion_codes`:
    esa cajita deja entrar un descuento que nuestra base no conoce.

    La `metadata` viaja como respaldo. La relación que manda es
    `PasarelaCheckout`, porque además de la cuenta guarda el sujeto y el idioma,
    que Stripe no conoce.

    `account=None` es la compra sin cuenta: la metadata no lleva `account_id`
    (la cuenta, si hay que crearla, sale del mail del pago). `terminos=True`
    pone la casilla obligatoria de aceptar los términos en el checkout.
    """
    prod = producto(codigo_producto)  # KeyError si no existe: lo dice el catálogo
    if prod.es_gratis:
        raise ValueError(f"{codigo_producto} es gratis: no se cobra")
    if not prod.vendible:
        raise ValueError(f"{codigo_producto} está retirado: no se vende")
    monto = prod.precio_en(moneda)  # KeyError si no se vende en esa moneda
    if not settings.STRIPE_SECRET_KEY:
        raise StripeNoConfigurado("STRIPE_SECRET_KEY no configurado")

    _validar_success_url(settings.STRIPE_SUCCESS_URL)

    product_id = product_de(codigo_producto)
    idioma = locale if locale in LOCALES else LOCALE_POR_DEFECTO
    metadata = {"account_id": str(account.pk)} if account is not None else {}
    if sujeto is not None:
        metadata["sujeto_id"] = str(sujeto.uuid)

    extra: dict = {}
    if cupon is not None:
        extra["discounts"] = [{"promotion_code": cupon.stripe_promotion_code_id}]

    if terminos:
        extra["consent_collection"] = {"terms_of_service": "required"}
    if moneda == "brl":
        # Pix sólo existe en reales. El IOF (3,5 %) lo absorbemos (decisión del
        # 13-10-2026, R4): quien paga ve en el banco exactamente lo que vio en
        # la página. El QR vence con la sesión.
        extra["payment_method_options"] = {
            "pix": {"amount_includes_iof": "always", "expires_after_seconds": VENCIMIENTO_PIX},
        }

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        sesion = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{
                "price_data": {
                    "product": product_id, "currency": moneda, "unit_amount": monto,
                    # Impuesto INCLUIDO en el precio publicado, como el default
                    # de la cuenta; explícito para no depender de ese default.
                    "tax_behavior": "inclusive",
                },
                "quantity": 1,
            }],
            **extra,
            # `managed_payments` EXPLÍCITO en cada sesión. No es obligatorio
            # —viene activado por defecto en la cuenta—, pero ese default es un
            # switch del dashboard con un "Turn off" al lado: si alguien lo
            # apaga, el cobro pasa a Stripe normal, el IVA de 80 países vuelve
            # a ser nuestro y el código no se entera. Sin error, sin log.
            managed_payments={"enabled": True},
            # Quien compra navegando en portugués ve el checkout en portugués y
            # vuelve a una página en portugués. `{CHECKOUT_SESSION_ID}` lo
            # reemplaza Stripe: es lo que la página de retorno usa para
            # preguntar en qué quedó la compra.
            locale=_LOCALE_STRIPE[idioma],
            success_url=settings.STRIPE_SUCCESS_URL.replace("{locale}", idioma),
            expires_at=int((timezone.now() + VENCIMIENTO_SESION).timestamp()),
            metadata=metadata,
        )
    except stripe.InvalidRequestError as exc:
        if cupon is not None and str(exc.param or "").startswith("discounts"):
            # No es una falla nuestra: el cupón se agotó (o venció, o se apagó)
            # entre que se validó acá y se abrió allá. Es la divergencia entre
            # el contador local y el de Stripe, y tiene que verse.
            logger.warning(
                "stripe rechazó el cupón %s al abrir el checkout de %s: %s",
                cupon.codigo, codigo_producto, exc.code,
            )
            raise CuponRechazado(exc.code or "coupon") from exc
        logger.exception("stripe no pudo abrir el checkout de %s", codigo_producto)
        raise StripeError(type(exc).__name__) from exc
    except stripe.StripeError as exc:
        # El mensaje puede traer el motivo, pero también detalle de la cuenta:
        # se loguea el producto y el tipo de error, no la respuesta cruda.
        logger.exception("stripe no pudo abrir el checkout de %s", codigo_producto)
        raise StripeError(type(exc).__name__) from exc

    return sesion.id, sesion.url


def crear_cupon(cupon) -> tuple[str, str]:
    """Crea en Stripe el Coupon y el Promotion Code de un cupón nuestro y
    devuelve `(coupon_id, promotion_code_id)`.

    El tope y el vencimiento van en los dos objetos: Stripe exige que los del
    promotion code no superen los del coupon, y dejarlos iguales es lo que
    hace que «se agotó» signifique lo mismo en los dos lados. Ninguno se puede
    editar después: para cambiar algo se desactiva y se crea otro.
    """
    if not settings.STRIPE_SECRET_KEY:
        raise StripeNoConfigurado("STRIPE_SECRET_KEY no configurado")
    productos = [product_de(codigo) for codigo in cupon.productos]
    vence = cupon.vence_at
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        coupon_params: dict = dict(
            percent_off=cupon.porcentaje, duration="once", max_redemptions=cupon.usos_maximos,
            applies_to={"products": productos}, name=cupon.codigo,
            metadata={"cupon_id": str(cupon.pk)},
        )
        promo_params: dict = dict(
            code=cupon.codigo, max_redemptions=cupon.usos_maximos,
            metadata={"cupon_id": str(cupon.pk)},
        )
        if vence is not None:
            coupon_params["redeem_by"] = int(vence.timestamp())
            promo_params["expires_at"] = int(vence.timestamp())
        coupon = stripe.Coupon.create(**coupon_params)
        promo = stripe.PromotionCode.create(
            promotion={"type": "coupon", "coupon": coupon.id}, **promo_params,
        )
    except stripe.StripeError as exc:
        logger.exception("stripe no pudo crear el cupón %s", cupon.codigo)
        raise StripeError(type(exc).__name__) from exc
    return coupon.id, promo.id


def activar_cupon(promotion_code_id: str, activo: bool) -> None:
    """Prende o apaga el Promotion Code. Reactivar uno agotado o vencido lo
    rechaza Stripe («permanently inactive»): se propaga como `StripeError`."""
    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        stripe.PromotionCode.modify(promotion_code_id, active=activo)
    except stripe.StripeError as exc:
        logger.exception("stripe no pudo cambiar active=%s de %s", activo, promotion_code_id)
        raise StripeError(type(exc).__name__) from exc
