"""Todo lo que habla con Stripe vive acá, y nada más lo importa.

La capa HTTP (`webhooks_stripe.py`, `checkout.py`) no conoce la librería: pide
por estas funciones. Así el día que Stripe cambie una firma de método, se toca
un archivo.
"""

import logging

import stripe
from django.conf import settings

logger = logging.getLogger(__name__)


class FirmaInvalida(Exception):
    """La entrega no viene de Stripe, o no viene entera."""


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
