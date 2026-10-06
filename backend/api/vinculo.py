"""Vínculo, fase 1: la vista previa pública.

Calcula dos cartas y cómo se miran, y no guarda nada: son datos de nacimiento
de dos personas que no aceptaron nada, y una de ellas ni siquiera está usando
el sitio. No llama al modelo: las frases son fijas (`api.vinculo_frases`). El
techo es el mismo `preview` de la carta suelta, porque lo que se puede quemar
desde acá es la misma CPU de efemérides.
"""

import logging

from django.conf import settings
from django.http import Http404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.chart_service import calcular
from api.views import _preview_repr
from api.vinculo_frases import PERSONALES, frase
from core.exceptions import CoreError
from core.sinastria import aspectos_cruzados

logger = logging.getLogger(__name__)

IDIOMAS = ("es", "en", "pt")
MAX_ASPECTOS = 4


def _exigir_flag() -> None:
    if not settings.VINCULO_PREVIEW_ENABLED:
        raise Http404


class VinculoEstadoView(APIView):
    """`GET /api/vinculo/`: si la vista previa está encendida. La web lo
    consulta para decidir si muestra las landings y si van al sitemap.

    Responde SIEMPRE 200, con el valor en el cuerpo. No es un detalle: el
    caché de datos de Next sólo guarda las respuestas 200, así que con un 404
    para «apagado» el valor viejo («encendido») quedaba vigente para siempre y
    apagar el flag no apagaba la landing. Un 200 con `preview: false` se cachea
    igual que uno con `true`. Es público y no revela nada que `/api/estado/` no
    diga ya."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"preview": bool(settings.VINCULO_PREVIEW_ENABLED)})


class VinculoPreviewView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "preview"

    def post(self, request):
        _exigir_flag()
        lang = request.data.get("lang")
        if lang not in IDIOMAS:
            lang = "es"
        try:
            a = calcular(request.data["a"])
            b = calcular(request.data["b"])
        except (KeyError, TypeError, ValueError, AttributeError, CoreError) as exc:
            # Sin payload ni exc_info: adentro hay fechas de nacimiento.
            logger.warning("vista previa de vínculo rechazada: %s", type(exc).__name__)
            return Response({"error": "datos_invalidos"}, status=status.HTTP_400_BAD_REQUEST)

        # `place_label` no está en `BirthInput`: mismas coordenadas con otro
        # nombre de lugar siguen siendo la misma persona.
        if a.birth_input == b.birth_input:
            return Response({"error": "misma_persona"}, status=status.HTTP_400_BAD_REQUEST)

        personales = [
            x for x in aspectos_cruzados(a.data, b.data)
            if x.p_a in PERSONALES and x.p_b in PERSONALES
        ][:MAX_ASPECTOS]

        return Response({
            "a": _preview_repr(a),
            "b": _preview_repr(b),
            "aspectos": [
                {"p_a": x.p_a, "p_b": x.p_b, "aspecto": x.aspecto,
                 "orbe": round(x.orbe, 2), "frase": frase(x.p_a, x.p_b, x.aspecto, lang)}
                for x in personales
            ],
        })
