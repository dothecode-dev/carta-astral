"""`POST /api/conteo/teaser/`: los pasos de quien calculó su carta sin cuenta.

Público, sin sesión y con techo por IP. No guarda nada de quién fue: suma uno
a un contador del día (`api.conteo.contar_teaser`). Lo que no está en la lista
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
