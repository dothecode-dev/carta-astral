"""Webhook de RevenueCat: acredita/revierte créditos IAP contra el ledger.

Idempotente por event.id. Autentica por header compartido. Ack (200) ante
casos ignorados (cuenta/producto/tipo desconocido) para cortar reintentos;
solo 401 ante fallo de auth. Ver mini-spec del plan para el mapeo de eventos,
que DEBE verificarse contra un webhook real antes de prod.

CANCELLATION (RevenueCat: el usuario apaga el auto-renew, NO implica
devolución de dinero) se excluye intencionalmente de REFUND_EVENTS para evitar
marcar usuarios legítimos. Task 7 debe confirmar — contra un evento real de
RevenueCat — cuál type dispara el reembolso de un CONSUMABLE; si los
consumables llegan como CANCELLATION con cancel_reason específico, re-agregar
ese gate aquí.
"""

import logging

from django.conf import settings
from django.utils.crypto import constant_time_compare
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api import ledger
from api.models import Account

logger = logging.getLogger(__name__)

PURCHASE_EVENTS = {"INITIAL_PURCHASE", "NON_RENEWING_PURCHASE"}
REFUND_EVENTS = {"REFUND"}


class RevenueCatWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        expected = settings.REVENUECAT_WEBHOOK_AUTH
        provided = request.headers.get("Authorization", "")
        if not expected or not constant_time_compare(provided, expected):
            logger.warning("revenuecat webhook: auth inválida")
            return Response({"error": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        body = request.data
        if not isinstance(body, dict):
            logger.warning("revenuecat webhook: body no es un objeto JSON")
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)
        event = body.get("event") or {}
        etype = event.get("type")
        event_id = event.get("id")
        app_user_id = event.get("app_user_id")
        product_id = event.get("product_id")

        if not event_id or not app_user_id:
            logger.warning("revenuecat webhook: evento sin id/app_user_id: %s", etype)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        try:
            account = Account.objects.get(pk=int(app_user_id))
        except (Account.DoesNotExist, ValueError, TypeError):
            logger.warning("revenuecat webhook: cuenta desconocida app_user_id=%s event=%s",
                           app_user_id, event_id)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        credits = settings.REVENUECAT_PRODUCT_CREDITS.get(product_id)
        if credits is None:
            logger.warning("revenuecat webhook: product_id sin mapeo: %s (event=%s)",
                           product_id, event_id)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        if etype in PURCHASE_EVENTS:
            applied = ledger.credit_purchase(account, credits, external_id=event_id,
                                             note=f"revenuecat:{product_id}")
        elif etype in REFUND_EVENTS:
            applied = ledger.refund_credits(account, credits, external_id=event_id,
                                            note=f"revenuecat-refund:{product_id}")
        else:
            logger.info("revenuecat webhook: tipo no manejado: %s (event=%s)", etype, event_id)
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        logger.info("revenuecat webhook: %s event=%s acc=%s applied=%s",
                    etype, event_id, account.id, applied)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
