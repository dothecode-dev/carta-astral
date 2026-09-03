"""Todo lo que habla con Stripe vive acá, y nada más lo importa.

La capa HTTP (`webhooks_stripe.py`, `checkout.py`) no conoce la librería: pide
por estas funciones. Así el día que Stripe cambie una firma de método, se toca
un archivo.
"""

import logging

import stripe
from django.conf import settings

from api.catalogo import producto

logger = logging.getLogger(__name__)


# Los idiomas que el sitio sirve, y que Stripe también soporta en su checkout.
# Lista blanca y no concatenación: el locale llega del navegador y termina en la
# URL a la que Stripe devuelve a la persona después de pagar.
LOCALES = ("es", "en", "pt")
LOCALE_POR_DEFECTO = "es"


class FirmaInvalida(Exception):
    """La entrega no viene de Stripe, o no viene entera."""


class StripeNoConfigurado(Exception):
    """Falta la clave, o el producto no tiene precio mapeado en Stripe."""


class StripeError(Exception):
    """Stripe respondió algo que no es una sesión.

    Propia y no `stripe.StripeError` a secas para que la vista pueda
    distinguirla y responder 502 sin dejar un `PasarelaCheckout` a medias.
    """


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


def codigo_de_producto(price_id: str) -> str:
    """El código del catálogo para ese precio de Stripe.

    Levanta `KeyError` si no lo mapeamos: acreditar un producto que no sabemos
    cuál es sería entregar cualquier cosa. El mapeo vive en `STRIPE_PRECIOS`
    porque los ids son distintos en test y en live —Stripe no los comparte
    entre modos— y el código tiene que ser el mismo en los dos.
    """
    return settings.STRIPE_PRECIOS[price_id]


def _price_de(codigo_producto: str) -> str:
    """El id del precio de Stripe para ese producto nuestro.

    `STRIPE_PRECIOS` mapea al revés (price de Stripe → código nuestro) porque
    así lo consume el webhook, que es quien recibe el id.
    """
    for price_id, codigo in settings.STRIPE_PRECIOS.items():
        if codigo == codigo_producto:
            return price_id
    # El catálogo y Stripe son dos listas que hay que mantener alineadas: mejor
    # fallar acá que abrir un pago que después nadie puede acreditar.
    raise StripeNoConfigurado(f"{codigo_producto} no tiene precio en Stripe")


def crear_checkout(
    account, codigo_producto: str, chart=None, locale: str = LOCALE_POR_DEFECTO,
) -> tuple[str, str]:
    """Abre una sesión de pago y devuelve `(session_id, url)`.

    `KeyError` si el producto no está en el catálogo, `ValueError` si es gratis
    y `StripeNoConfigurado` si falta la clave o el precio: los tres son errores
    de configuración nuestra, no de quien compra.

    La `metadata` viaja como respaldo. La relación que manda es
    `PasarelaCheckout`, porque además de la cuenta guarda la carta y el idioma,
    que Stripe no conoce.
    """
    prod = producto(codigo_producto)  # KeyError si no existe: lo dice el catálogo
    if prod.precio_centavos == 0:
        raise ValueError(f"{codigo_producto} es gratis: no se cobra")
    if not settings.STRIPE_SECRET_KEY:
        raise StripeNoConfigurado("STRIPE_SECRET_KEY no configurado")

    price_id = _price_de(codigo_producto)
    idioma = locale if locale in LOCALES else LOCALE_POR_DEFECTO
    metadata = {"account_id": str(account.pk)}
    if chart is not None:
        metadata["chart_id"] = str(chart.pk)

    stripe.api_key = settings.STRIPE_SECRET_KEY
    try:
        sesion = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price": price_id, "quantity": 1}],
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
            locale=idioma,
            success_url=settings.STRIPE_SUCCESS_URL.replace("{locale}", idioma),
            metadata=metadata,
        )
    except stripe.StripeError as exc:
        # El mensaje puede traer el motivo, pero también detalle de la cuenta:
        # se loguea el producto y el tipo de error, no la respuesta cruda.
        logger.exception("stripe no pudo abrir el checkout de %s", codigo_producto)
        raise StripeError(type(exc).__name__) from exc

    return sesion.id, sesion.url
