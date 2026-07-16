from django.http import HttpRequest, JsonResponse
from django.urls import include, path

from api.legal import legal_page


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness para Coolify: el proceso responde. No toca la DB a propósito."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz),
    path("api/", include("api.urls")),
    path("legal/privacy", legal_page, {"doc": "privacy"}),
    path("legal/terms", legal_page, {"doc": "terms"}),
]
