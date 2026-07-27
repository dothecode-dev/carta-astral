import os

from django.contrib import admin
from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from api.legal import legal_page

# El admin es de SÓLO LECTURA (ver api/admin.py) y vive en una ruta que se
# configura por entorno: sin ADMIN_URL no se monta, así que en un despliegue que
# no la setee directamente no existe. No se usa "admin/" por defecto para no
# regalarle la puerta a los bots que la escanean.
ADMIN_URL = os.environ.get("ADMIN_URL", "").strip("/")


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness para Coolify: el proceso responde. No toca la DB a propósito."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz),
    path("api/", include("api.urls")),
    path("legal/privacy", legal_page, {"doc": "privacy"}),
    path("legal/terms", legal_page, {"doc": "terms"}),
]

if ADMIN_URL:
    urlpatterns.append(path(f"{ADMIN_URL}/", admin.site.urls))
