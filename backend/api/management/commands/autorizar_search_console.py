"""Consigue el refresh token para leer Search Console. Se corre UNA vez.

    python manage.py autorizar_search_console

Abre la autorización de Google en el navegador, espera el regreso en un puerto
local y muestra el refresh token, que va a `GSC_REFRESH_TOKEN` en el despliegue.

**Por qué esto y no una cuenta de servicio:** Google bloquea la creación de sus
claves con la Organization Policy `iam.disableServiceAccountKeyCreation`, que
viene activada por defecto. Un refresh token de la cuenta que ya es dueña de la
propiedad no necesita ninguna excepción de política, no le da acceso a nadie
nuevo, y se revoca desde la propia cuenta de Google.

El permiso pedido es de SOLO LECTURA (`webmasters.readonly`): el informe mira.

Corre en la máquina de quien autoriza, no en el servidor: necesita un navegador
y un puerto local al que Google pueda volver.
"""

import http.server
import secrets
import threading
import urllib.parse
import webbrowser

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.informe_actividad import SCOPE_GSC

#: Tiene que estar declarado igual en el cliente OAuth, en "Authorized redirect
#: URIs". Google exige coincidencia exacta, puerto incluido.
PUERTO = 8765
REDIRECT = f"http://localhost:{PUERTO}/"


class _Recibe(http.server.BaseHTTPRequestHandler):
    """Atiende el regreso de Google y se queda con el código."""

    codigo = None
    estado = None

    def do_GET(self):  # noqa: N802 — lo nombra la librería estándar
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        _Recibe.codigo = (params.get("code") or [None])[0]
        _Recibe.estado = (params.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        mensaje = "Listo, ya podés cerrar esta pestaña." if _Recibe.codigo else "No llegó ningún código."
        self.wfile.write(f"<p style='font:16px system-ui'>{mensaje}</p>".encode())

    def log_message(self, *args):
        """Silencio: el log de esta librería ensucia la salida del comando."""


class Command(BaseCommand):
    help = "Obtiene el refresh token de Google para leer Search Console."

    def handle(self, *args, **options):
        if not settings.GSC_CLIENT_ID or not settings.GSC_CLIENT_SECRET:
            raise CommandError(
                "Faltan GSC_CLIENT_ID y GSC_CLIENT_SECRET. Se crean en la consola de "
                "Google como cliente OAuth de tipo 'Web application', con "
                f"{REDIRECT} entre las Authorized redirect URIs.",
            )

        estado = secrets.token_urlsafe(16)
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
            "client_id": settings.GSC_CLIENT_ID,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPE_GSC,
            # Sin `offline` Google devuelve un token de una hora y ningún
            # refresh token, que es justamente lo que se vino a buscar.
            "access_type": "offline",
            # Y sin `consent` no lo devuelve la SEGUNDA vez: si esta cuenta ya
            # autorizó antes, Google asume que el token anterior sigue guardado.
            "prompt": "consent",
            "state": estado,
        })

        servidor = http.server.HTTPServer(("localhost", PUERTO), _Recibe)
        hilo = threading.Thread(target=servidor.handle_request, daemon=True)
        hilo.start()

        self.stdout.write("Autorizá en el navegador. Si no se abre solo, entrá acá:\n")
        self.stdout.write(f"{url}\n")
        webbrowser.open(url)

        hilo.join(timeout=300)
        servidor.server_close()

        if not _Recibe.codigo:
            raise CommandError("No llegó el código de Google (¿se canceló, o pasaron 5 minutos?)")
        if _Recibe.estado != estado:
            # Defensa contra que otra pestaña mande un código ajeno a este puerto.
            raise CommandError("El `state` no coincide: se descarta la respuesta")

        respuesta = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": _Recibe.codigo,
                "client_id": settings.GSC_CLIENT_ID,
                "client_secret": settings.GSC_CLIENT_SECRET,
                "redirect_uri": REDIRECT,
                "grant_type": "authorization_code",
            },
            timeout=30,
        )
        if respuesta.status_code >= 400:
            raise CommandError(f"Google rechazó el canje ({respuesta.status_code}): {respuesta.text[:300]}")

        token = respuesta.json().get("refresh_token")
        if not token:
            raise CommandError(
                "Google no devolvió refresh_token. Suele pasar cuando la cuenta ya había "
                "autorizado esta app: revocá el acceso en https://myaccount.google.com/permissions "
                "y probá de nuevo.",
            )

        self.stdout.write(self.style.SUCCESS("\nGSC_REFRESH_TOKEN (copialo al despliegue):"))
        self.stdout.write(token)
        self.stdout.write(
            "\nNo lo guardes en el repo: es público. Google lo caduca si pasa seis "
            "meses sin usarse, y se revoca desde tu cuenta cuando quieras.",
        )
