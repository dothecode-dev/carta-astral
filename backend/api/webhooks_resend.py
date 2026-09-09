"""El webhook de rebotes de Resend: RF15.

Hoy, si un código de acceso rebota, no queda rastro en ningún lado: el
síntoma es silencio y alguien que dice «no me llegó». Esto no acredita ni
cobra nada —a diferencia de `webhooks_stripe.py`— y no escribe en la base:
lo único que hace es dejar un rastro logueado (y, por la integración de
logging de Sentry, un evento allá) para poder cruzar un reclamo con el
`resend_id` que `api/notificaciones.py` ya loguea al mandar el mail.

La URL es pública, así que la firma es la única autenticación. Sin
`RESEND_WEBHOOK_SECRET` configurado se rechaza todo (fail-closed): aceptar
entregas cuando falta la configuración es la peor forma de fallar.

**Política de códigos de respuesta.** Svix (el proveedor de webhooks que usa
Resend) reintenta con backoff exponencial durante unas 37 horas desde el
primer intento (inmediato, 5 s, 5 min, 30 min, 2 h, 5 h, 10 h, 10 h) y recién
deshabilita el endpoint si TODAS las entregas fallan durante 5 días seguidos
(docs.svix.com/retries, leído el 09-09-2026). Es la misma familia que
Stripe —reintenta con backoff y no apaga nada al primer tropiezo—, así que
la política es la misma:

- firma inválida → **403**: no es un problema que un reintento arregle, y
  responder 2xx a una firma que no verifica lo confirmaría como un endpoint
  válido para cualquiera que la adivine.
- evento que no nos interesa → **200**: no hay nada que hacer con él.
- cualquier fallo inesperado al procesar un evento que sí nos interesa →
  **5xx**: a diferencia del webhook de Stripe, acá no hay ninguna operación
  de negocio (no se acredita ni se escribe nada) que pueda fallar de forma
  DEFINITIVA —no hay un precio sin mapear, ni un monto que no cierra—, así
  que no hay un fallo que sepamos de antemano que reintentar no vaya a
  arreglar. Todo lo inesperado se trata como transitorio y se deja para el
  próximo reintento, con margen de sobra: un deploy tarda 2-3 minutos.
"""

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.resend_client import FirmaInvalida, verificar_firma

logger = logging.getLogger(__name__)

# Los únicos dos eventos que nos interesan. El resto (`email.delivered`,
# `email.sent`, etc.) se ignora: no hay ningún reclamo que resolver con ellos.
EVENTOS_QUE_NOS_INTERESAN = ("email.bounced", "email.complained")


class ResendWebhookView(APIView):
    # La firma es la autenticación: `AllowAny` no apaga nada más (ver el
    # hallazgo del review del CMS), sólo dice que acá no hay sesión que valga.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        secreto = settings.RESEND_WEBHOOK_SECRET
        if not secreto:
            logger.error("RESEND_WEBHOOK_SECRET no configurado: se rechaza la entrega")
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            evento = verificar_firma(request.body, request.headers, secreto)
        except FirmaInvalida as e:
            logger.warning("entrega de resend rechazada: %s", e)
            return Response(status=status.HTTP_403_FORBIDDEN)

        tipo = evento.get("type", "")
        if tipo not in EVENTOS_QUE_NOS_INTERESAN:
            logger.info("evento de resend ignorado: %s", tipo)
            return Response(status=status.HTTP_200_OK)

        try:
            _registrar(tipo, evento)
        except Exception:
            # Transitorio hasta que se demuestre lo contrario (ver el
            # docstring del módulo): no hay una rama de fallo definitivo acá.
            logger.exception("entrega de resend %s fallida: se pide reintento", tipo)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)


def _registrar(tipo: str, evento: dict) -> None:
    """Deja el rastro. Con el mismo `resend_id` que loguea `notificaciones.py`
    al mandar el mail, para poder cruzar los dos.

    La dirección (`data.to`) NUNCA va al log: mismo criterio que el resto del
    módulo de notificaciones. `logger.error` y no `.warning` a propósito: es
    el nivel que la integración de logging de Sentry convierte en evento
    (ver `config/observabilidad.py`), y el objetivo de este webhook es
    justamente dejar de estar en silencio.
    """
    resend_id = (evento.get("data") or {}).get("email_id")
    logger.error(
        "%s de resend", tipo,
        extra={"evento": tipo, "resend_id": resend_id},
    )
