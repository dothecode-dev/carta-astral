"""Vistas HTTP de «pagar es entrar»: la lógica vive en `api/compra_anonima.py`.

Módulo propio por el mismo criterio que `cupones_api.py` y `compras_api.py`:
`checkout.py` ya roza el techo de ~250 líneas.
"""

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.exceptions import CoreError

from api import compra_anonima, cupones, mantenimiento, stripe_client
from api.chart_service import calcular
from api.checkout import _idioma, _respuesta_de_stripe

logger = logging.getLogger(__name__)

_NO_DISPONIBLE = {"error": "el cobro no está disponible"}


class CheckoutAnonimoView(APIView):
    """`POST /api/checkout/anonimo/`: abre el pago del informe natal sin cuenta.

    Pagar es entrar: la cuenta se crea (o se encuentra) en el webhook, por el
    mail del pago. Acá se guarda la carta, se abre Stripe y se devuelve un
    nonce que la web guarda en una cookie propia de ESE checkout; el
    `checkout_id` solo no alcanza para entrar después.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "checkout_anonimo"

    def post(self, request):
        # Los dos 503 van antes de mirar el cuerpo (RF4): con el sitio cerrado
        # o sin la clave que el webhook necesita, no hay nada que validar.
        if mantenimiento.activo():
            return Response(
                {"error": "estamos actualizando el sitio, probá en unos minutos"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        try:
            compra_anonima.comprobar_disponible()
        except compra_anonima.NoDisponible:
            logger.error("checkout anónimo sin TOMBSTONE_HMAC_KEY: no se abre")
            return Response(_NO_DISPONIBLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        idioma = _idioma(request)
        # Misma validación que la vista previa (`calcular`), ANTES de crear
        # nada. Sin `exc_info` ni payload en el log: es la fecha de nacimiento
        # de alguien que todavía no aceptó nada.
        try:
            calcular(request.data)
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("checkout anónimo rechazado: %s", type(exc).__name__)
            return Response(
                {"error": str(exc), "motivo": "datos_invalidos"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            fila, nonce = compra_anonima.abrir(request.data, idioma, request.data.get("cupon"))
        except compra_anonima.NoDisponible:
            return Response(_NO_DISPONIBLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except compra_anonima.CuponNoAdmitido:
            return Response(
                {"error": "el cupón no sirve sin cuenta", "motivo": "requiere_cuenta"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except cupones.CuponInvalido as exc:
            logger.info("cupón rechazado en checkout anónimo: %s", exc.motivo)
            return Response(
                {"error": "el cupón no sirve", "motivo": cupones.motivo_publico(exc.motivo)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (KeyError, ValueError):
            # El producto es fijo: que el catálogo no lo conozca, lo retire o
            # lo tenga gratis es configuración nuestra, no un pedido mal armado.
            logger.exception("checkout anónimo: el producto %r no se puede vender", compra_anonima.PRODUCTO)
            return Response(_NO_DISPONIBLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (stripe_client.StripeNoConfigurado, stripe_client.StripeError) as exc:
            return _respuesta_de_stripe(exc, compra_anonima.PRODUCTO)
        return Response({"url": fila.url, "checkout_id": fila.checkout_id, "nonce": nonce})
