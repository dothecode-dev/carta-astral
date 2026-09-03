"""Todo lo que habla con Stripe vive acá, y nada más lo importa.

La capa HTTP (`webhooks_stripe.py`, `checkout.py`) no conoce la librería: pide
por estas funciones. Así el día que Stripe cambie una firma de método, se toca
un archivo.
"""

import logging

import stripe

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
