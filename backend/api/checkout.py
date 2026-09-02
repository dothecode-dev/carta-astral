"""`POST /api/checkout/`: abre una sesión de pago en Polar.

En módulo propio y no en `api/views.py`, que ya pasó las 250 líneas que el
CLAUDE.md marca como techo — mismo criterio que `api/webhooks.py`.

Lo único que llega del navegador es QUÉ producto se compra y, opcionalmente,
sobre qué carta. El precio no: lo pone el catálogo al abrir el checkout, y el
webhook lo vuelve a validar contra la orden antes de otorgar nada.
"""

import logging

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from api import polar
from api.auth import AccountTokenAuthentication
from api.permissions import HasAccount
from api.models import Chart, PolarCheckout

logger = logging.getLogger(__name__)


class CheckoutView(APIView):
    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]

    def post(self, request):
        codigo = request.data.get("producto")
        if not codigo:
            return Response(
                {"error": "falta el producto"}, status=status.HTTP_400_BAD_REQUEST
            )

        # La carta se resuelve contra la cuenta que pide: sin ese filtro se
        # compra un informe y se lo entrega en la carta de otro.
        carta = None
        chart_id = request.data.get("chart_id")
        if chart_id:
            carta = get_object_or_404(Chart, uuid=chart_id, account=request.user)

        try:
            checkout_id, url = polar.crear_checkout(request.user, codigo, chart=carta)
        except (KeyError, ValueError) as exc:
            # Producto que no está en el catálogo, o gratis. Es un pedido mal
            # armado, no una falla nuestra.
            logger.warning("checkout rechazado para %r: %s", codigo, exc)
            return Response({"error": "producto inválido"}, status=status.HTTP_400_BAD_REQUEST)
        except polar.PolarNoConfigurado:
            # Falta el token o la ficha en Polar: problema de configuración
            # nuestro, no de quien compra.
            logger.exception("checkout sin configurar para %r", codigo)
            return Response(
                {"error": "el cobro no está disponible"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except polar.PolarError:
            logger.exception("polar no pudo abrir el checkout de %r", codigo)
            return Response(
                {"error": "no pudimos abrir el pago"}, status=status.HTTP_502_BAD_GATEWAY
            )

        # Después del éxito y no antes: una fila huérfana dejaría que el webhook
        # de otra orden resolviera contra ella.
        PolarCheckout.objects.create(
            checkout_id=checkout_id, account=request.user, codigo_producto=codigo, chart=carta,
        )
        return Response({"url": url})
