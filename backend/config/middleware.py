"""Middleware solo-desarrollo. Se monta únicamente con DEBUG=1 (ver settings)."""

from django.http import HttpResponse


class DevCorsMiddleware:
    """CORS abierto para que la build web de desarrollo de la app (expo web en
    localhost) pueda pegarle al backend local. La app nativa no usa CORS y en
    prod este middleware no existe."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            response = HttpResponse()
        else:
            response = self.get_response(request)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "authorization, content-type"
        response["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response
