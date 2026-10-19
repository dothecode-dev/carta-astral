"""Webhook de Mercado Pago: firma y despacho, nada más.

La traducción de un pago a `cobro` vive en `api.pasarelas.mercadopago`; acá
sólo se decide si la notificación es nuestra y auténtica, y qué código HTTP
devolver. Mismas reglas que `webhooks_stripe`: lo definitivo es 200 (un
reintento no lo arregla) y lo transitorio, 500 para que MP reintente.

MP manda cada pago dos veces por dos canales: el webhook (`?data.id=…&type=…`,
firmado) y el IPN viejo (`?id=…&topic=…`, sin firma). Sólo se atiende el
webhook; el IPN se contesta 200 sin leer nada, para que no se reintente.
Además de `payment` se atienden reclamos (`topic_claims_integration_wh`) y
contracargos (`topic_chargebacks_wh`), firmados igual; el resto, 200 sin leer.
"""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.pasarelas import mercadopago
from api.pasarelas.mercadopago_firma import verificar

logger = logging.getLogger(__name__)

_RECLAMO = "topic_claims_integration_wh"
_CONTRACARGO = "topic_chargebacks_wh"
_ATENDIDOS = ("payment", _RECLAMO, _CONTRACARGO)


class MercadoPagoWebhookView(APIView):
    # La firma es la autenticación (ver `StripeWebhookView`).
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        tipo = request.query_params.get("type", "")
        if tipo not in _ATENDIDOS:
            # IPN (`topic=`) u otro tipo de notificación: nada que hacer.
            logger.info(
                "notificación de mercadopago ignorada: type=%r topic=%r",
                tipo, request.query_params.get("topic", ""),
            )
            return Response(status=status.HTTP_200_OK)

        secreto = settings.MP_WEBHOOK_SECRET
        if not secreto:
            logger.error("MP_WEBHOOK_SECRET no configurado: se rechaza la notificación")
            return Response(status=status.HTTP_401_UNAUTHORIZED)

        # El id firmado es el de la query, no el del cuerpo. En reclamos y
        # contracargos es el uuid de la notificación (medido en sandbox): los
        # ids de negocio vienen en el cuerpo, que NO está firmado.
        data_id = str(request.query_params.get("data.id", ""))
        firma_ok = verificar(
            request.headers.get("x-signature", ""), request.headers.get("x-request-id", ""), data_id, secreto,
        )
        if not firma_ok:
            logger.warning("notificación de mercadopago con firma inválida (data.id=%r)", data_id)
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        if not data_id:
            logger.warning("notificación de mercadopago firmada sin data.id")
            return Response(status=status.HTTP_400_BAD_REQUEST)

        if tipo == _RECLAMO:
            mercadopago.procesar_reclamo(_dato(request, "id"))
            return Response(status=status.HTTP_200_OK)

        try:
            if tipo == _CONTRACARGO:
                mercadopago.procesar_contracargo(_dato(request, "id"), _dato(request, "payment_id"))
            else:
                mercadopago.procesar_pago(data_id)
        except Exception:
            # Transitorio hasta que se demuestre lo contrario (ver
            # `webhooks_stripe`): lo definitivo ya volvió sin levantar.
            logger.exception("notificación de mercadopago %s (%s) fallida: se pide reintento", data_id, tipo)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)


def _dato(request, clave: str) -> str:
    """`data.<clave>` del cuerpo como texto; vacío si no está o no es un id."""
    try:
        cuerpo = request.data
    except ParseError:
        logger.warning("notificación de mercadopago firmada con un cuerpo que no es JSON")
        return ""
    if not isinstance(cuerpo, dict):
        return ""
    data = cuerpo.get("data")
    valor = data.get(clave) if isinstance(data, dict) else None
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        return ""
    return str(valor)
