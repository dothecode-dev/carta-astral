"""`GET /api/moneda/`: en qué moneda ve los precios quien pregunta.

La web lo consulta en cada página con precio y lo guarda en una cookie que la
persona puede cambiar. Público y sin caché: la respuesta es por IP.
"""

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api import geo
from config.axes_ip import ip_del_cliente


class MonedaView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        pais = geo.pais_de(ip_del_cliente(request))
        return Response({"moneda": geo.moneda_para(pais), "pais": pais})
