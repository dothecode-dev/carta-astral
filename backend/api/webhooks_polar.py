"""Webhook de Polar: lo que entra por acá es plata.

La URL es pública y no tiene sesión: lo único que separa un pago real de uno
inventado es la **firma**, y por eso se verifica antes de mirar el contenido.
Un payload sin firmar no merece ni que lo parseemos.

Responde 2xx a casi todo, incluidos los casos que ignora: Polar deshabilita un
endpoint tras diez entregas fallidas seguidas, y un 4xx por un evento que no nos
interesa dejaría sin webhook a los que sí. El 403 de firma inválida es la
excepción a propósito — eso no es un caso a ignorar, es alguien golpeando.

Sólo se escuchan `order.paid` y `order.refunded`:

- `order.created` llega con la orden en `pending`: la plata no está confirmada.
- `order.updated` se emite JUNTO CON `order.paid`, con la misma orden. Escuchar
  los dos acredita dos veces la misma compra.
"""

import json
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from standardwebhooks.webhooks import Webhook, WebhookVerificationError

from api import notificaciones, polar
from api.canje import MontoInvalido, aplicar_compra, revocar
from api.models import Account, PolarCheckout

logger = logging.getLogger(__name__)

# Los únicos dos que mueven derechos. Cualquier otro se responde 2xx y se
# descarta sin tocar nada.
EVENTOS = ("order.paid", "order.refunded")


def _estructura(dato, profundidad=0):
    """La FORMA del payload, sin sus valores.

    Sirve para corregir el mapeo cuando llegue el primer evento real sin
    volcar al log el detalle de una compra —ni montos, ni ids, ni el mail de
    quien pagó—. Mismo helper que usa el webhook de RevenueCat.
    """
    if profundidad > 3:
        return "..."
    if isinstance(dato, dict):
        return {k: _estructura(v, profundidad + 1) for k, v in dato.items()}
    if isinstance(dato, list):
        return [_estructura(dato[0], profundidad + 1)] if dato else []
    return type(dato).__name__


class PolarWebhookView(APIView):
    # La firma es la autenticación: `AllowAny` no apaga nada más (ver el
    # hallazgo del review del CMS), sólo dice que acá no hay sesión que valga.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        secreto = settings.POLAR_WEBHOOK_SECRET
        if not secreto:
            # Fail-closed: sin con qué verificar no se confía en nadie.
            # Aceptar todo cuando falta la configuración es la peor forma de
            # fallar en un endpoint por el que entra plata.
            logger.error("POLAR_WEBHOOK_SECRET no configurado: se rechaza la entrega")
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            # Sobre `request.body` (bytes) y no `request.data`: la firma cubre
            # el cuerpo EXACTO que mandó Polar, y volver a serializar el dict
            # parseado da otros bytes.
            evento = Webhook(secreto).verify(request.body, dict(request.headers))
        except (WebhookVerificationError, ValueError):
            logger.warning("entrega de polar con firma inválida")
            return Response(status=status.HTTP_403_FORBIDDEN)

        if isinstance(evento, (str, bytes)):
            evento = json.loads(evento)

        tipo = evento.get("type", "")
        if tipo not in EVENTOS:
            logger.info("evento de polar ignorado: %s", tipo)
            return Response(status=status.HTTP_200_OK)

        # La estructura, no los valores: es lo que deja corregir el mapeo
        # cuando llegue el primer evento real (Task 7 del plan).
        orden = evento.get("data") or {}
        logger.info("evento de polar %s con forma %s", tipo, _estructura(orden))

        if tipo == "order.paid":
            _acreditar(orden)
        elif tipo == "order.refunded":
            _reembolsar(orden)
        return Response(status=status.HTTP_200_OK)


def _resolver_cuenta_y_checkout(orden: dict):
    """A quién le corresponde esta orden, y con qué carta si vino de una.

    Manda `PolarCheckout` porque `order.checkout_id` es lo único que Polar
    garantiza; la `metadata` es respaldo, porque su propagación del checkout a
    la orden no está en el contrato publicado (se confirmó leyendo su fuente,
    que puede cambiar).
    """
    fila = PolarCheckout.objects.filter(checkout_id=orden.get("checkout_id", "")).first()
    if fila is not None and fila.account is not None:
        return fila.account, fila

    account_id = (orden.get("metadata") or {}).get("account_id")
    if account_id:
        cuenta = Account.objects.filter(pk=account_id).first()
        if cuenta is not None:
            return cuenta, None
    return None, None


def _acreditar(orden: dict) -> None:
    """Traduce la orden a un otorgamiento. Nunca levanta: cualquier problema se
    loguea y la entrega se responde 2xx igual, porque diez fallidas seguidas
    dejan sin webhook a todos los pagos que vengan después."""
    order_id = orden.get("id", "")
    cuenta, fila = _resolver_cuenta_y_checkout(orden)
    if cuenta is None:
        logger.error("orden %s sin cuenta que la reclame: no se acredita", order_id)
        return

    try:
        codigo = polar.codigo_de_producto(orden.get("product_id", ""))
    except KeyError:
        logger.error("orden %s de un producto que no mapeamos: no se acredita", order_id)
        return

    if fila is not None and fila.codigo_producto != codigo:
        # El checkout se abrió para un producto y la orden dice otro. No es un
        # caso que sepamos resolver, y elegir mal significa entregar de más o
        # de menos: se registra y no se acredita.
        logger.error(
            "orden %s: el checkout era de %s y la orden dice %s",
            order_id, fila.codigo_producto, codigo,
        )
        return

    try:
        aplicado = aplicar_compra(
            cuenta, codigo, orden.get("net_amount"),
            external_id=f"polar:order:{order_id}",
            chart=fila.chart if fila is not None else None,
        )
    except MontoInvalido:
        # Ya lo logueó `aplicar_compra` con los dos montos: acá no se repite.
        return
    except Exception:
        logger.exception("no se pudo acreditar la orden %s", order_id)
        return

    if aplicado:
        notificaciones.notificar(
            cuenta, "compra_acreditada", {"producto": codigo}, lang="es",
        )


def _reembolsar(orden: dict) -> None:
    """Revoca lo comprado y anota como deuda lo que ya se usó.

    No se le quita a nadie un informe ya entregado: `canje.revocar` baja el
    derecho hasta donde alcanza y manda el resto a deuda, que se cancela contra
    la próxima compra. Es la política que decidimos el 02-09-2026, en contra de
    lo que decía el plan viejo.

    `external_id` lleva el prefijo `polar:refund:` y no `polar:order:`: comparten
    el id de la orden, y con la misma clave el reembolso se descartaría como
    duplicado del pago que lo precedió.

    Como `_acreditar`, nunca levanta: la entrega se responde 2xx igual.
    """
    order_id = orden.get("id", "")
    cuenta, fila = _resolver_cuenta_y_checkout(orden)

    try:
        codigo = polar.codigo_de_producto(orden.get("product_id", ""))
    except KeyError:
        logger.error("reembolso de %s: producto que no mapeamos, no se revoca", order_id)
        return

    if cuenta is None and fila is None:
        logger.error("reembolso de %s sin checkout ni cuenta: no se revoca", order_id)
        return

    try:
        # `cuenta` puede ser None si la cuenta se borró después de comprar
        # (RF22): `revocar` lo contempla y registra el movimiento igual, para
        # que la contabilidad cierre aunque no haya a quién cobrarle.
        revocar(cuenta, codigo, 1, external_id=f"polar:refund:{order_id}")
    except Exception:
        logger.exception("no se pudo revocar el reembolso de la orden %s", order_id)
