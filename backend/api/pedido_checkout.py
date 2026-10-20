"""Lo que las vistas de checkout (con cuenta y sin cuenta) leen del pedido y
cómo le responden a quien compra cuando la pasarela no abre el pago.

Fuera de `checkout.py` porque lo comparte `compra_anonima_api.py`, y `checkout.py` tiene el techo de ~250 líneas.
"""

import logging

from rest_framework import status
from rest_framework.response import Response

from api import apertura, catalogo

logger = logging.getLogger(__name__)


class MonedaInvalida(Exception):
    """El cliente pidió una moneda que no conocemos o en la que ese producto
    no se vende."""


def moneda_pedida(request, codigo_producto: str) -> str:
    """En qué moneda se cobra: la que manda el cliente (RF4), y si no manda
    ninguna, `usd`. La IP NO decide el cobro (decisión del 18-10-2026): sólo
    sugiere qué mostrar por `/api/moneda/`. Si decidiera, una web que muestra
    US$ abriría un pago en reales sin que nadie lo vea.

    Se normaliza —`BRL ` llega de un cliente que no es la web— y se valida
    contra las monedas del producto: no se inventa un precio en una moneda que
    el catálogo no tiene (EC2). Un producto desconocido no es un problema de
    moneda: lo rechaza quien ya lo rechazaba."""
    explicita = request.data.get("moneda")
    pedida = str(explicita).strip().lower() if explicita else catalogo.MONEDA_BASE
    prod = catalogo.CATALOGO.get(codigo_producto)
    if prod is None:
        return pedida
    if pedida not in prod.monedas():
        raise MonedaInvalida(pedida)
    if not catalogo.moneda_habilitada(pedida):
        raise MonedaInvalida(pedida)
    return pedida


MONEDA_INVALIDA = {"error": "moneda inválida", "motivo": "moneda_invalida"}


def respuesta_de_pasarela(exc, codigo) -> Response:
    """Qué le decimos a quien compra cuando la pasarela no abre el pago."""
    if isinstance(exc, apertura.ERRORES_MP):
        logger.error("mercado pago no pudo abrir el checkout de %r: %s", codigo, type(exc).__name__)
        return Response({"error": "el cobro no está disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, apertura.STRIPE_NO_CONFIGURADO):
        # Falta la clave o el precio en Stripe: problema de configuración
        # nuestro, no de quien compra.
        logger.exception("checkout sin configurar para %r", codigo)
        return Response(
            {"error": "el cobro no está disponible"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, apertura.CUPON_RECHAZADO):
        # Ya lo logueó `crear_checkout` con el código. Para quien compra es
        # «se agotó»: la alternativa —abrirle el pago a precio de lista—
        # sería cobrarle de más a alguien que creía tener descuento.
        return Response(
            {"error": "el cupón no sirve", "motivo": "agotado"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    logger.exception("stripe no pudo abrir el checkout de %r", codigo)
    return Response({"error": "no pudimos abrir el pago"}, status=status.HTTP_502_BAD_GATEWAY)
