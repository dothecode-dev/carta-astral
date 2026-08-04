import os

from django.conf import settings
from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import include, path
from django.views.static import serve

from api.legal import legal_page
from cms import api as cms_api

# El admin es de SÓLO LECTURA (ver api/admin.py) y vive en una ruta que se
# configura por entorno: sin ADMIN_URL no se monta, así que en un despliegue que
# no la setee directamente no existe. No se usa "admin/" por defecto para no
# regalarle la puerta a los bots que la escanean.
ADMIN_URL = os.environ.get("ADMIN_URL", "").strip("/")

# El admin del CMS, igual que el de Django: sólo existe si el entorno lo pide,
# y en una ruta que no es la que escanean los bots.
WAGTAIL_ADMIN_URL = os.environ.get("WAGTAIL_ADMIN_URL", "").strip("/")


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness para Coolify: el proceso responde. No toca la DB a propósito."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz),
    path("api/", include("api.urls")),
    path("cms/api/v2/", include((cms_api.api_router.get_urlpatterns(), "wagtailapi"))),
    path("legal/privacy", legal_page, {"doc": "privacy"}),
    path("legal/terms", legal_page, {"doc": "terms"}),
]

# Las imágenes del CMS se sirven con `django.views.static.serve`, no con
# WhiteNoise: WhiteNoise indexa sus archivos una sola vez al arrancar (salvo
# `WHITENOISE_AUTOREFRESH`, desaconsejado en producción y no acotable a un
# solo directorio), así que una imagen subida después de ese arranque
# quedaría sin servir hasta el próximo restart. `serve` lee del disco en
# cada request, que es justo lo que hace falta para contenido que cambia en
# runtime. El tráfico es bajo (un solo editor) y el proceso ya está detrás
# del proxy de Coolify, así que el costo de no tener gzip/sendfile acá es
# aceptable.
urlpatterns.append(
    path("media/<path:path>", serve, {"document_root": settings.MEDIA_ROOT})
)

if ADMIN_URL:
    urlpatterns.append(path(f"{ADMIN_URL}/", admin.site.urls))

if WAGTAIL_ADMIN_URL:
    from wagtail.admin import urls as wagtailadmin_urls

    urlpatterns.append(path(f"{WAGTAIL_ADMIN_URL}/", include(wagtailadmin_urls)))
