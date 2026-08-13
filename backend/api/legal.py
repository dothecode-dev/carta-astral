"""Redirección de las páginas legales hacia la web.

Los textos ya no viven acá: están versionados en `web/content/legal/` y los
renderiza el sitio, en los tres idiomas y con el diseño del producto. Lo que
antes verificaba `tests/api/test_legal_pages.py` sobre el contenido (que
mencione el hash del borrado, los procesadores y el disclaimer de no-consejo)
lo verifica ahora `web/scripts/check-legal.mjs`, que corre en el mismo CI.

Estas rutas quedan porque las versiones de la app ya instaladas las tienen
compiladas adentro (`carta-astral-app/src/legal/urls.ts`) y porque mantenerlas
no cuesta nada.

Es 302 y no 301 a propósito: el dominio de la web puede volver a cambiar, y un
redirect permanente queda cacheado en los navegadores durante meses.
"""

from django.conf import settings
from django.http import HttpRequest, HttpResponseRedirect

LANGS = ("es", "en", "pt")


def legal_page(request: HttpRequest, doc: str) -> HttpResponseRedirect:
    lang = request.GET.get("lang", "es")
    if lang not in LANGS:
        lang = "es"
    # De `settings`, que ya exige la variable en producción y cae a
    # localhost:3000 en desarrollo. Leerla acá por separado —como se hacía—
    # significaba dos fuentes de verdad que además divergían: el default era el
    # dominio viejo, así que en desarrollo estas rutas mandaban a un sitio
    # ajeno en vez de a la web local.
    base = settings.WEB_BASE_URL.rstrip("/")
    return HttpResponseRedirect(f"{base}/{lang}/legal/{doc}")
