"""Vistas de la sesión.

Fuera de `auth.py` a propósito: ese módulo es el que DRF carga para autenticar
cada pedido, así que importar `APIView` ahí crea un ciclo de imports al arrancar.
"""

from rest_framework import status
from rest_framework.authentication import get_authorization_header
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from api.identity import hash_token
from api.models import Session


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
