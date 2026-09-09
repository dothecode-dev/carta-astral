"""Vistas de la sesión.

Fuera de `auth.py` a propósito: ese módulo es el que DRF carga para autenticar
cada pedido, así que importar `APIView` ahí crea un ciclo de imports al arrancar.
"""

import logging

from django.core.exceptions import ImproperlyConfigured
from django.db.models import F
from rest_framework import status
from rest_framework.authentication import get_authorization_header
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import codigos_acceso, notificaciones
from api.accounts import resolve_account
from api.auth import create_session
from api.canje import derechos_de
from api.identity import hash_token, tombstone_hmac_configurada
from api.models import CodigoAcceso, Session
from api.sso import VerifiedIdentity

logger = logging.getLogger(__name__)


class LogoutView(APIView):
    """Cierra la sesión con la que se hizo el pedido, y sólo esa.

    Borra la fila de Session: el token deja de servir en el acto. Las demás
    sesiones de la misma cuenta —el teléfono, otro navegador— siguen abiertas,
    que es lo que espera cualquiera al salir de un lugar y no de todos.
    """

    def post(self, request: Request) -> Response:
        token = get_authorization_header(request).split()[1].decode()
        Session.objects.filter(token_hash=hash_token(token)).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PedirCodigoView(APIView):
    """Pide (o reenvía) el código de acceso por mail — RF6/RF9.

    Devuelve 202 SIEMPRE, sin una sola rama condicional por existencia de
    cuenta: el envío del mail ocurre en las dos ramas, así que tampoco hay
    diferencia de tiempo explotable. Distinguir revelaría quién tiene cuenta
    en un sitio de astrología. Ninguna rama loguea la dirección ni el código.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request: Request) -> Response:
        email = request.data.get("email") or ""
        if not email:
            return Response({"error": "email requerido"}, status=status.HTTP_400_BAD_REQUEST)
        lang = request.data.get("lang") or "es"
        destino = request.data.get("destino") or ""

        try:
            fila, claro, _reenvio = codigos_acceso.pedir(email, destino=destino)
        except codigos_acceso.DemasiadosPedidos:
            return Response(
                {"error": "demasiados pedidos"}, status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        try:
            notificaciones.enviar_codigo(fila.email, claro, lang)
        except notificaciones.EnvioFallido as exc:
            logger.error("no se pudo enviar el código de acceso: %s", exc)
            # El cupo de la hora (RF9) frena el bombardeo de una bandeja
            # ajena: un mail que no salió no bombardeó a nadie, así que se
            # devuelve (Ruling 13). `F("envios") - 1` para no perder un
            # reenvío concurrente que haya incrementado la fila entre medio.
            CodigoAcceso.objects.filter(pk=fila.pk).update(envios=F("envios") - 1)
            return Response({"error": "login no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response({}, status=status.HTTP_202_ACCEPTED)


class CanjearCodigoView(APIView):
    """Canjea el código de acceso por una sesión — RF7.

    Misma forma de respuesta que `/api/auth/google` (`token`, `derechos`,
    `account_id`), más `destino` (RF16): la web lo necesita para volver a
    donde estaba, porque en iOS el `next` de la URL no sobrevive el viaje a
    Mail y de vuelta.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request: Request) -> Response:
        email = request.data.get("email") or ""
        codigo = request.data.get("codigo") or ""
        if not email or not codigo:
            return Response(
                {"error": "email y codigo requeridos"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not tombstone_hmac_configurada():
            # Chequeo ANTES de tocar la fila del código (C2, revisión de
            # `puertas-de-acceso`): `canjear()` marca `usado_en` dentro de su
            # propio `select_for_update()` —a propósito, es lo que sostiene
            # la concurrencia de dos pestañas canjeando a la vez— así que un
            # 503 posterior a esa llamada ya había quemado el código en un
            # login que no llegó a ocurrir. Medido en staging: la fila
            # quedaba usada y sin cuenta creada, y sin la clave cargada eso
            # pasaba en el 100% de los intentos. Acá no se tocó nada todavía,
            # así que el mismo código sirve una vez que la configuración se
            # arregle.
            logger.error("login por mail no disponible: falta TOMBSTONE_HMAC_KEY")
            return Response({"error": "login no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            fila = codigos_acceso.canjear(email, codigo)
        except codigos_acceso.CodigoInvalido:
            return Response({"error": "código inválido"}, status=status.HTTP_401_UNAUTHORIZED)

        # La identidad se arma con el email de la FILA (ya normalizado por
        # `codigos_acceso.pedir`/`canjear`), nunca con el string crudo del
        # request (Ruling 11b): si no, dos casings de la misma dirección
        # terminan en dos cuentas.
        vid = VerifiedIdentity(
            provider="email", sub=fila.email, email=fila.email, email_verified=True,
        )
        try:
            account = resolve_account(vid)
        except ImproperlyConfigured as exc:
            # Defensa en profundidad: el precheck de arriba ya debería evitar
            # llegar acá (TOCTOU aparte, es la misma clave). El código, en
            # este punto, ya se consumió — ver la nota de C2 en el reporte
            # sobre por qué el caso general de "cualquier fallo de
            # resolve_account()" no se cierra acá.
            logger.error("login por mail no disponible: %s", exc)
            return Response({"error": "login no disponible"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        token = create_session(account)
        return Response({
            "token": token,
            "derechos": derechos_de(account),
            "account_id": account.id,
            "destino": fila.destino,
        })
