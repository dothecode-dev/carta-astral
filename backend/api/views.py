import logging

from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.exceptions import CoreError
from interpret.exceptions import InterpretationError

from api import geocode
from api.chart_service import create_chart
from api.interpretation_service import (
    DISCLAIMERS,
    CapReached,
    get_or_create_interpretation,
)
from api.models import Chart

logger = logging.getLogger(__name__)

_INTERPRETATION_LANGS = ("es", "en", "pt")


def _chart_repr(chart: Chart) -> dict:
    return {
        "id": str(chart.uuid),
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "engine_version": chart.engine_version,
    }


class ChartCreateView(APIView):
    def post(self, request):
        try:
            chart = create_chart(request.data)
        except (KeyError, ValueError, CoreError) as exc:
            logger.warning("chart creation rejected: %s", exc, exc_info=True)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_chart_repr(chart), status=status.HTTP_201_CREATED)


class ChartDetailView(APIView):
    def get(self, request, uuid):
        chart = get_object_or_404(Chart, uuid=uuid)
        return Response(_chart_repr(chart))


class GeocodeView(APIView):
    def post(self, request):
        q = request.data.get("q", "")
        try:
            results = geocode.search(q)
        except ValueError as exc:
            logger.warning("geocode query rejected: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"results": results})


class InterpretationView(APIView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "interpretation"

    def post(self, request, uuid):
        lang = request.data.get("lang", "es")
        if lang not in _INTERPRETATION_LANGS:
            return Response(
                {"error": f"lang debe ser uno de {_INTERPRETATION_LANGS}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        chart = get_object_or_404(Chart, uuid=uuid)
        try:
            interp = get_or_create_interpretation(chart, lang)
        except CapReached:
            return Response(
                {"error": "límite diario de interpretaciones alcanzado, probá más tarde"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except InterpretationError as exc:
            logger.warning("interpretation generation failed: %s", exc, exc_info=True)
            return Response(
                {"error": "no se pudo generar la interpretación"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "text": interp.text,
                "lang": interp.lang,
                "prompt_version": interp.prompt_version,
                "disclaimer": DISCLAIMERS[interp.lang],
                "created_at": interp.created_at.isoformat(),
            }
        )
