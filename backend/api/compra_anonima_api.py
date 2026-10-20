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

from api import apertura, catalogo, compra_anonima, compra_anonima_apertura, mantenimiento
from api.chart_service import calcular, mensaje_de_datos_invalidos, validar_trato
from api.pedido_checkout import (
    MONEDA_INVALIDA,
    MonedaInvalida,
    idioma_pedido,
    moneda_pedida,
    respuesta_de_pasarela,
)
from api.identity import mail_valido
from api.models import MailBloqueado

logger = logging.getLogger(__name__)

_NO_DISPONIBLE = {"error": "el cobro no está disponible"}
_NO_ENCONTRADO = {"error": "no encontrado"}


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

        # Sin cuenta no hay cupón (review 07-10): «uno por cuenta» no se puede
        # aplicar a nadie, y la compra podía terminar en una cuenta que ya lo
        # usó. La web no lo manda desde la vista previa; el mismo texto que
        # ya muestra para este motivo lo manda a entrar con el mail.
        if request.data.get("cupon"):
            return Response(
                {"error": "el cupón no sirve sin cuenta", "motivo": "requiere_cuenta"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        idioma = idioma_pedido(request)
        try:
            moneda = moneda_pedida(request, compra_anonima.PRODUCTO)
        except MonedaInvalida:
            return Response(MONEDA_INVALIDA, status=status.HTTP_400_BAD_REQUEST)
        # En pesos el mail se pide acá: MP no devuelve el de quien paga.
        email = ""
        if catalogo.pasarela_de(moneda) == "mercadopago":
            email = mail_valido(request.data.get("email"))
            if email is None:
                return Response(
                    {"error": "hace falta un mail válido", "motivo": "email_invalido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Como `CheckoutView` con una cuenta bloqueada, y antes de guardar
            # la carta o abrir la preferencia (decisión de Gustavo, 19-10). En
            # dólares el mail no se pide y Stripe sigue como estaba.
            if MailBloqueado.bloqueado(email):
                logger.warning("checkout anónimo en pesos con un mail bloqueado: no se abre")
                return Response({"error": "cuenta bloqueada", "motivo": "bloqueado"}, status=status.HTTP_403_FORBIDDEN)
        # Misma validación que la vista previa (`calcular`), ANTES de crear
        # nada. Sin `exc_info` ni payload en el log: es la fecha de nacimiento
        # de alguien que todavía no aceptó nada.
        try:
            calcular(request.data)
            validar_trato(request.data.get("trato"))
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("checkout anónimo rechazado: %s", type(exc).__name__)
            return Response(
                {"error": mensaje_de_datos_invalidos(exc), "motivo": "datos_invalidos"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            fila, nonce = compra_anonima_apertura.abrir(request.data, idioma, moneda, email)
        except compra_anonima.NoDisponible:
            return Response(_NO_DISPONIBLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except (KeyError, ValueError):
            # El producto es fijo: que el catálogo no lo conozca, lo retire o
            # lo tenga gratis es configuración nuestra, no un pedido mal armado.
            logger.exception("checkout anónimo: el producto %r no se puede vender", compra_anonima.PRODUCTO)
            return Response(_NO_DISPONIBLE, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except apertura.ERRORES_DE_PASARELA as exc:
            return respuesta_de_pasarela(exc, compra_anonima.PRODUCTO)
        return Response({"url": fila.url, "checkout_id": fila.checkout_id, "nonce": nonce})


class CheckoutCanjeView(APIView):
    """`POST /api/checkout/anonimo/canjear/`: la vuelta de Stripe (RF10-RF13).

    La web manda el `checkout_id` y el nonce que guardó en la cookie de ese
    checkout. Responde `sesion` (con el token), `codigo` (con el mail
    enmascarado) o `pendiente`; cualquier otra cosa es el mismo 404 genérico,
    sin decir qué condición falló (RF11).

    Sin chequeo de mantenimiento a propósito (RF14b): quien pagó durante un
    deploy no puede quedar frente a un 503. Throttle propio (`canje_compra`),
    no el `auth` del login: la web lo sondea mientras está `pendiente`
    (RF13), y con el balde compartido un webhook lento dejaría a quien pagó
    sin poder entrar por código o Google el resto del día.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "canje_compra"

    def post(self, request):
        checkout_id = request.data.get("checkout_id")
        nonce = request.data.get("nonce")
        if not isinstance(checkout_id, str) or not isinstance(nonce, str):
            return Response(_NO_ENCONTRADO, status=status.HTTP_404_NOT_FOUND)
        resultado = compra_anonima.canjear(checkout_id, nonce)
        if resultado["estado"] == "invalido":
            return Response(_NO_ENCONTRADO, status=status.HTTP_404_NOT_FOUND)
        return Response(resultado)
