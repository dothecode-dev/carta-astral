"""Redirección de las páginas legales hacia la web.

Los textos ya no viven acá: están versionados en `web/content/legal/` y los
renderiza el sitio, en los tres idiomas y con el diseño del producto. Lo que
antes verificaba `tests/api/test_legal_pages.py` sobre el contenido (que
mencione el hash del borrado, los procesadores y el disclaimer de no-consejo)
lo verifica ahora `web/scripts/check-legal.mjs`, que corre en el mismo CI.

Estas rutas quedan porque las versiones de la app ya instaladas las tienen
compiladas adentro (`carta-astral-app/src/legal/urls.ts`) y porque mantenerlas
no cuesta nada.

Es 302 y no 301 a propósito: `astra.dothecode.com` es un dominio provisional, y
un redirect permanente queda cacheado en los navegadores durante meses.
"""

import os

from django.http import HttpRequest, HttpResponseRedirect

LANGS = ("es", "en", "pt")

WEB_BASE_URL = os.environ.get("WEB_BASE_URL", "https://astra.dothecode.com").rstrip("/")


def legal_page(request: HttpRequest, doc: str) -> HttpResponseRedirect:
    lang = request.GET.get("lang", "es")
    if lang not in LANGS:
        lang = "es"
    return HttpResponseRedirect(f"{WEB_BASE_URL}/{lang}/legal/{doc}")
