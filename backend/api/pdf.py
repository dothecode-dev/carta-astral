"""La capa HTTP del PDF.

Vive en su propio módulo y no en `views.py` por lo mismo que `sky.py` y
`webhooks.py`: `views.py` ya está en 278 líneas y sumarle un endpoint con su
propio contrato no lo mejora.
"""

import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from api.auth import AccountTokenAuthentication
from api.chart_pdf_service import PdfGenerationError, pdf_filename, render_pdf
from api.models import Chart
from api.pdf_payload import ChartPdfSerializer
from api.permissions import HasAccount

logger = logging.getLogger(__name__)


class ChartPdfView(APIView):
    """El PDF de una carta propia.

    Es POST y no GET porque el cuerpo trae la geometría de la rueda, que el
    navegador ya calculó: el backend no sabe dibujarla y no tiene por qué.
    No cobra créditos ni dispara ninguna generación —lee lo que ya existe—,
    pero cuesta CPU, y de ahí el scope propio de throttle.
    """

    authentication_classes = [AccountTokenAuthentication]
    permission_classes = [HasAccount]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "pdf"

    def post(self, request, uuid):
        chart = get_object_or_404(Chart, uuid=uuid, account=request.user)

        serializer = ChartPdfSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("pdf: payload rechazado para la carta %s", chart.uuid)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            pdf = render_pdf(chart, serializer.validated_data)
        except PdfGenerationError:
            # render_pdf ya dejó el log con la causa.
            return Response(
                {"error": "no se pudo generar el PDF"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # El nombre del archivo sale de la carta, no del payload: el rótulo que
        # manda el cliente es para el documento, y para el disco vale lo que la
        # carta se llama de verdad. Si no tiene nombre, el rótulo traducido
        # ("Carta sin nombre") es mejor que un archivo llamado ".pdf".
        ascii_name, utf8_name = pdf_filename(
            chart.birth_data.name or serializer.validated_data["labels"]["chart_name"]
        )
        respuesta = HttpResponse(pdf, content_type="application/pdf")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
        )
        return respuesta
