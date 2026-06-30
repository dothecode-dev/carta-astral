from django.http import HttpRequest, JsonResponse
from django.urls import include, path


def healthz(_request: HttpRequest) -> JsonResponse:
    """Liveness para Coolify: el proceso responde. No toca la DB a propósito."""
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("healthz/", healthz),
    path("api/", include("api.urls")),
]
