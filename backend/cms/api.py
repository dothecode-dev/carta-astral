"""La API de contenido que consume la web.

Es pública a propósito: el frontend la lee en el build para generar las notas
como HTML estático. No expone nada que no esté publicado.
"""

from rest_framework.permissions import AllowAny
from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.api.v2.views import PagesAPIViewSet
from wagtail.images.api.v2.views import ImagesAPIViewSet


class NotasAPIViewSet(PagesAPIViewSet):
    # El permiso global del proyecto es `HasAccount`; sin esto la web recibiría
    # 401 al pedir las notas.
    permission_classes = [AllowAny]


class PortadasAPIViewSet(ImagesAPIViewSet):
    permission_classes = [AllowAny]


api_router = WagtailAPIRouter("wagtailapi")
api_router.register_endpoint("pages", NotasAPIViewSet)
api_router.register_endpoint("images", PortadasAPIViewSet)
