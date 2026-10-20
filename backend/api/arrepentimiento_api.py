"""`POST /api/arrepentimiento/`: el botón de arrepentimiento (RA3).

Público, sin sesión y con techo por IP. Responde lo mismo haya o no compras
con ese mail: no puede servir para averiguar quién compró.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api import arrepentimiento
from api.reglas_checkout import idioma_pedido
from api.identity import mail_valido


class ArrepentimientoView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "arrepentimiento"

    def post(self, request):
        email = mail_valido(request.data.get("email"))
        if email is None:
            return Response(
                {"error": "hace falta un mail válido", "motivo": "email_invalido"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        numero = request.data.get("numero_compra")
        solicitud = arrepentimiento.registrar(
            email, numero if isinstance(numero, str) else "", idioma_pedido(request),
        )
        return Response({"codigo": solicitud.codigo}, status=status.HTTP_201_CREATED)
