"""Modo vidriera: el sitio como muestra de trabajo, sin cobro ni cuentas.

Con `MODO_VIDRIERA=1` queda viva sólo la parte que no cobra, no guarda datos
de nadie y no gasta en el modelo. Lo demás responde 404: no hay nadie del otro
lado reintentando (las pasarelas ya no apuntan acá), así que conviene no
anunciar qué rutas existen.

La regla es la lista de lo ABIERTO. `api/urls.py` le pone la guarda a toda
ruta que no esté acá, así que una ruta nueva nace cerrada en la vidriera.

El flag se lee en cada pedido y no al armar las rutas: es lo que deja
probarlo con `settings` en los tests, y cuesta una lectura de atributo.
"""

from functools import wraps

from django.conf import settings
from django.http import JsonResponse

#: Rutas de `api/urls.py` (tal como se declaran) que siguen vivas en vidriera.
ABIERTAS = frozenset({
    "catalogo/", "moneda/", "charts/preview/", "geocode/", "sky/", "sky/moon/",
    "estado/", "conteo/teaser/", "conteo/visita/", "vinculo/", "vinculo/preview/",
})


def activa() -> bool:
    return bool(settings.MODO_VIDRIERA)


def cerrada(vista):
    """Envuelve una vista: en vidriera responde 404 sin llegar a ejecutarla."""

    @wraps(vista)
    def guarda(request, *args, **kwargs):
        if activa():
            return JsonResponse(
                {"detail": "no disponible en esta versión de muestra", "code": "vidriera"}, status=404,
            )
        return vista(request, *args, **kwargs)

    guarda.cerrada_en_vidriera = True  # type: ignore[attr-defined]
    return guarda
