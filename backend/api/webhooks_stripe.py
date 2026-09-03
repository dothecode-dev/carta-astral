"""El webhook de Stripe: por acá entra la plata.

La URL es pública, así que la firma es la única autenticación. Sin
`STRIPE_WEBHOOK_SECRET` configurado se rechaza todo (fail-closed): aceptar
entregas cuando falta la configuración es la peor forma de fallar en un
endpoint por el que se acreditan informes pagos.
"""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.stripe_client import FirmaInvalida, verificar_firma

logger = logging.getLogger(__name__)


class StripeWebhookView(APIView):
    # La firma es la autenticación: `AllowAny` no apaga nada más (ver el
    # hallazgo del review del CMS), sólo dice que acá no hay sesión que valga.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        secreto = settings.STRIPE_WEBHOOK_SECRET
        if not secreto:
            logger.error("STRIPE_WEBHOOK_SECRET no configurado: se rechaza la entrega")
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            evento = verificar_firma(
                request.body, request.headers.get("Stripe-Signature", ""), secreto,
            )
        except FirmaInvalida as e:
            logger.warning("entrega de stripe rechazada: %s", e)
            return Response(status=status.HTTP_403_FORBIDDEN)

        # El ruteo a `_acreditar` y `_reembolsar` llega en los pasos 3 y 5 de la
        # spec, con sus tests. Hasta entonces cualquier evento se responde 200 y
        # se descarta, que es lo que corresponde a un evento que no escuchamos.
        logger.info("evento de stripe recibido: %s", evento.get("type", ""))
        return Response(status=status.HTTP_200_OK)
