"""El cielo de este momento, público y sin datos de nadie.

Lo consume la portada del sitio para dibujar la rueda. Es la única ruta de datos
sin autenticación del proyecto, así que tiene tres muros: cache, throttle y una
respuesta que no puede filtrar nada personal porque no recibe ningún dato.

Vive fuera de `views.py` porque ese archivo ya está en el límite de tamaño que
fija CLAUDE.md.
"""

from datetime import datetime, timezone

from django.core.cache import cache
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.ephemeris import sky_now

# El payload cambia una vez por minuto; el margen extra evita recalcular justo
# en el borde cuando dos pedidos caen a caballo del cambio de minuto.
CACHE_TTL_SECONDS = 90


class SkyView(APIView):
    """GET /api/sky/ — posiciones geocéntricas del minuto actual.

    Geocéntricas quiere decir medidas desde el centro de la Tierra: son iguales
    para cualquier observador, así que no hace falta preguntar dónde está quien
    mira. Por lo mismo no hay Ascendente ni casas, que sí dependen del lugar.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "sky"

    def get(self, request: Request) -> Response:
        moment = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        key = f"sky:{moment.isoformat()}"

        payload = cache.get(key)
        if payload is None:
            payload = {
                "moment": moment.isoformat(),
                "bodies": [
                    {
                        "name": p.name,
                        "sign": p.sign,
                        "longitude": round(p.abs_pos, 4),
                        "retrograde": p.retrograde,
                    }
                    for p in sky_now(moment)
                ],
            }
            cache.set(key, payload, CACHE_TTL_SECONDS)

        return Response(payload)
