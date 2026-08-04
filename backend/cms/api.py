"""La API de contenido que consume la web.

Es pública a propósito: el frontend la lee en el build para generar las notas
como HTML estático. No expone nada que no esté publicado.
"""

from rest_framework.permissions import AllowAny
from wagtail.api.v2.router import WagtailAPIRouter
from wagtail.api.v2.views import PagesAPIViewSet


class NotasAPIViewSet(PagesAPIViewSet):
    # `AllowAny` sólo desactiva el permiso global del proyecto (`HasAccount`);
    # la AUTENTICACIÓN global (`AccountTokenAuthentication`) seguiría corriendo
    # antes que él, y DRF propaga `AuthenticationFailed` aunque el permiso sea
    # AllowAny: un `Authorization: Bearer <token vencido>` convertía este
    # endpoint público en un 401. Vaciar `authentication_classes` es lo que
    # hace que un token de la app no tenga ninguna influencia acá — y de paso
    # deja de consultar `api.models.Session` en cada request al CMS.
    authentication_classes = []
    permission_classes = [AllowAny]


api_router = WagtailAPIRouter("wagtailapi")
api_router.register_endpoint("pages", NotasAPIViewSet)

# El endpoint `images` de Wagtail NO se registra a propósito. `ImagesAPIViewSet`
# no filtra por publicación —sólo excluye colecciones con restricción de vista,
# y la colección Root no tiene ninguna—, así que expuesto con AllowAny listaba
# todas las imágenes subidas, con su `title` y su `download_url`: la portada de
# una nota todavía en borrador quedaba pública antes de publicarla. La web no lo
# necesita: las portadas viajan ya resueltas dentro de la respuesta de páginas
# (`portada_tarjeta` y `portada_cabecera`, `cms/models.py`). Si algún día hace
# falta, se registra con el filtro por notas publicadas puesto desde el día uno.
