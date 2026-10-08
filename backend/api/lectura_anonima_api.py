"""HTTP de la lectura breve sin cuenta. La lógica está en `api.lectura_anonima`.

El throttle por IP NO va en `throttle_classes`: contaría los GET de la
consulta y los reintentos por «ocupado». Se llama a mano desde `pedir`, sólo
cuando el pedido va a escribir (spec 2026-10-08, RF13).
"""
import logging
import re

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import lectura_anonima
from api.chart_service import calcular, mensaje_de_datos_invalidos, validar_trato
from api.interpretation_service import DISCLAIMERS
from api.serializers import serialize_chart_data
from core.exceptions import CoreError

logger = logging.getLogger(__name__)

# El id que la web genera por cada pedido (`crypto.randomUUID()`). Se valida
# como un string corto y acotado porque se guarda tal cual en la caché.
_PEDIDO = re.compile(r"[0-9a-f-]{36}")

_RESPUESTAS = {
    lectura_anonima.Mantenimiento: (503, "mantenimiento", "estamos actualizando el sitio, probá en unos minutos"),
    lectura_anonima.Usado: (409, "usado", "este navegador ya usó su lectura gratis"),
    lectura_anonima.Ocupado: (503, "ocupado", "estamos escribiendo muchas lecturas, probá en unos segundos"),
    lectura_anonima.PorIP: (429, "ip", "demasiadas lecturas desde esta conexión por hoy"),
    lectura_anonima.SinCupo: (503, "cupo", "por hoy no hay más lecturas gratis"),
}


class LecturaAnonimaView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []
    throttle_scope = "lectura_anonima"

    def post(self, request):
        datos = request.data if isinstance(request.data, dict) else {}
        lang = datos.get("lang")
        try:
            if not isinstance(lang, str) or lang not in DISCLAIMERS:
                raise ValueError("lang inválido")
            pedido_id = datos.get("pedido")
            if not isinstance(pedido_id, str) or not _PEDIDO.fullmatch(pedido_id):
                raise ValueError("pedido inválido")
            trato = validar_trato(datos.get("trato"))
            carta = calcular(datos)
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("lectura anónima rechazada: %s", type(exc).__name__)
            return Response(
                {"error": mensaje_de_datos_invalidos(exc), "motivo": "datos"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        token = request.headers.get("X-Lectura-Token") or None
        try:
            pedido = lectura_anonima.pedir(
                serialize_chart_data(carta.data), lang, trato, token,
                permitir=lambda: ScopedRateThrottle().allow_request(request, self),
                pedido=pedido_id,
            )
        except tuple(_RESPUESTAS) as exc:
            codigo, motivo, texto = _RESPUESTAS[type(exc)]
            return Response({"error": texto, "motivo": motivo}, status=codigo)
        return Response({"token": pedido.token, "estado": pedido.estado}, status=status.HTTP_202_ACCEPTED)

    def get(self, request):
        token = request.headers.get("X-Lectura-Token")
        resultado = lectura_anonima.estado(token) if token else None
        if resultado is None:
            return Response({"error": "no hay lectura"}, status=status.HTTP_404_NOT_FOUND)
        return Response(resultado)

    def delete(self, request):
        """El acuse de recibo (spec §11): la web ya guardó la lectura `lista` y
        pide borrarla. `pedido` va en la query o en el cuerpo."""
        datos = request.data if isinstance(request.data, dict) else {}
        pedido_id = request.query_params.get("pedido") or datos.get("pedido")
        if not isinstance(pedido_id, str) or not _PEDIDO.fullmatch(pedido_id):
            return Response({"error": "pedido inválido", "motivo": "datos"}, status=status.HTTP_400_BAD_REQUEST)
        token = request.headers.get("X-Lectura-Token")
        if not token or not lectura_anonima.acusar(token, pedido_id):
            return Response({"error": "no hay lectura"}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
