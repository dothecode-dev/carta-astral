from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from api.chart_service import create_chart
from api.models import Chart


def _chart_repr(chart: Chart) -> dict:
    return {
        "id": chart.id,
        "house_system": chart.house_system,
        "zodiac": chart.zodiac,
        "data": chart.data,
        "engine_version": chart.engine_version,
    }


class ChartCreateView(APIView):
    def post(self, request):
        chart = create_chart(request.data)
        return Response(_chart_repr(chart), status=status.HTTP_201_CREATED)


class ChartDetailView(APIView):
    def get(self, request, pk):
        chart = get_object_or_404(Chart, pk=pk)
        return Response(_chart_repr(chart))
