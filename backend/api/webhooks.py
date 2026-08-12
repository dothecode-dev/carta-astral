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

# Nadie vio todavía un payload REAL de RevenueCat: estos alias evitan que una
# compra pagada se pierda si el campo viene con otro nombre. El orden importa:
# el primero que exista gana.
ALIAS_EVENT_ID = ("id", "event_id")
ALIAS_APP_USER = ("app_user_id", "original_app_user_id")
ALIAS_PRODUCT = ("product_id", "product_identifier")


def _primero(event: dict, claves) -> str | None:
    """Primer valor no vacío entre varios nombres posibles del mismo campo."""
    for clave in claves:
        valor = event.get(clave)
        if valor not in (None, ""):
            return valor
    return None


def _estructura(valor, profundidad: int = 2):
    """Forma del payload SIN los valores: sólo nombres de claves.

    Es lo que permite corregir el mapeo cuando llega un evento inesperado, sin
    volcar al log el email ni los datos del comprador.
    """
    if isinstance(valor, dict):
        if profundidad <= 0:
            return sorted(valor.keys())
        return {k: _estructura(v, profundidad - 1) for k, v in sorted(valor.items())}
    if isinstance(valor, list):
        return [_estructura(valor[0], profundidad - 1)] if valor else []
    return type(valor).__name__


class RevenueCatWebhookView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        if not settings.IAP_WEBHOOK_ENABLED:
            # 503 y no 404: un 404 le dice a RevenueCat que el endpoint no
            # existe, y tras unas cuantas respuestas así desactiva el webhook.
            # Con Retry-After el reintento queda en pie para cuando vuelva la app.
            return Response(
                {"error": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "3600"},
            )

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
        event_id = _primero(event, ALIAS_EVENT_ID)
        app_user_id = _primero(event, ALIAS_APP_USER)
        product_id = _primero(event, ALIAS_PRODUCT)

        if not event_id or not app_user_id:
            logger.warning(
                "revenuecat webhook: evento sin id/app_user_id: %s | estructura=%s",
                etype, _estructura(body),
            )
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        try:
            account = Account.objects.get(pk=int(app_user_id))
        except (Account.DoesNotExist, ValueError, TypeError):
            # Puede ser una cuenta borrada... o que el id venga en otro campo:
            # la estructura del payload lo desambigua.
            logger.warning(
                "revenuecat webhook: cuenta desconocida app_user_id=%s event=%s | estructura=%s",
                app_user_id, event_id, _estructura(body),
            )
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        credits = settings.REVENUECAT_PRODUCT_CREDITS.get(product_id)
        if credits is None:
            # El product_id NO es dato personal y es exactamente lo que hay que
            # agregar a REVENUECAT_PRODUCT_CREDITS: va entero al log.
            logger.warning(
                "revenuecat webhook: product_id sin mapeo: %s (event=%s) | conocidos=%s",
                product_id, event_id, sorted(settings.REVENUECAT_PRODUCT_CREDITS),
            )
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        if etype in PURCHASE_EVENTS:
            applied = ledger.credit_purchase(account, credits, external_id=event_id,
                                             note=f"revenuecat:{product_id}")
        elif etype in REFUND_EVENTS:
            applied = ledger.refund_credits(account, credits, external_id=event_id,
                                            note=f"revenuecat-refund:{product_id}")
        else:
            # CANCELLATION cae acá a propósito: en consumibles no implica
            # devolución de dinero, así que no descuenta. Queda registrado para
            # poder revisarlo contra el dashboard si alguna vez no cuadra.
            logger.info(
                "revenuecat webhook: tipo no manejado: %s (event=%s acc=%s) | estructura=%s",
                etype, event_id, account.id, _estructura(body),
            )
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        logger.info("revenuecat webhook: %s event=%s acc=%s applied=%s",
                    etype, event_id, account.id, applied)
        return Response({"status": "ok"}, status=status.HTTP_200_OK)
