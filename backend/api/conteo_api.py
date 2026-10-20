"""Contadores que alimenta el navegador: los pasos del teaser sin cuenta
(`POST /api/conteo/teaser/`) y las visitas (`POST /api/conteo/visita/`).

Los dos son públicos, sin sesión y con techo por IP. No guardan nada de quién
fue: suman uno a contadores del día (`api.conteo`). Lo que no está en una lista
cerrada se rechaza sin contar.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import conteo


class ConteoTeaserView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conteo"

    def post(self, request):
        if not conteo.contar_teaser(request.data.get("evento"), request.data.get("moneda")):
            return Response({"error": "evento desconocido"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConteoVisitaView(APIView):
    """`POST /api/conteo/visita/`: una página abierta en el sitio. Público y
    con techo por IP; la IP sólo se usa para saber el país, y no se guarda."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "conteo"

    def post(self, request):
        pais = conteo.pais_del_pedido(request)
        if not conteo.contar_visita(request.data.get("seccion"), request.data.get("procedencia"), pais):
            return Response({"error": "sección desconocida"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
