"""El PDF de un vínculo (RF24). Decisión del 10-10-2026: dos ruedas, una por
persona —como la vista previa—, los aspectos cruzados y el informe. La rueda
doble superpuesta queda fuera.

Reusa las piezas del PDF de la carta (`chart_pdf_service`): el dibujo de la
rueda, el escape, la lectura. Todo lo que viene del usuario —los alias, los
rótulos— pasa por `_esc`; los alias del informe se sustituyen antes de que
`_seccion_html` escape cada párrafo.
"""

import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from api.chart_pdf_service import (
    PdfGenerationError,
    _base_css,
    _esc,
    _font_css,
    _reading_for,
    _reading_html,
    _svg,
    pdf_filename,
    render_html,
)
from api.models import Sujeto
from api.pdf_payload import VinculoPdfSerializer
from api.vinculo_api import _Base, sustituir_alias
from api.vinculo_service import alias

logger = logging.getLogger(__name__)


def build_vinculo_html(sujeto: Sujeto, data: dict) -> str:
    """El documento entero como HTML. Función pura: es donde se verifica todo."""
    labels = data["labels"]
    ruedas = "".join(
        f'<div class="wheel-big">{_svg(rueda)}</div>' for rueda in data["wheels"] if rueda
    )
    filas_aspectos = "".join(
        f'<tr><td class="glyph">{_esc(a["glyph"])}</td>'
        f'<td>{_esc(a["name"])}</td>'
        f'<td class="data">{_esc(a["detail"])}</td><td></td></tr>'
        for a in data["aspects"]
    )
    seccion_aspectos = (
        f'<div class="section eyebrow">{_esc(labels["aspects"])}</div><table>{filas_aspectos}</table>'
        if data["aspects"] else ""
    )
    alias_ = alias(sujeto)
    lectura = _reading_for(
        sujeto, data.get("reading_lang"), transformar=lambda t: sustituir_alias(t, alias_),
    )
    bloque_lectura = (
        _reading_html(lectura[0], lectura[1], labels["reading"]) if lectura else ""
    )
    return f"""<meta charset="utf-8">
<style>
{_font_css()}
{_base_css()}
</style>
<div class="cover">
  <div class="brand">ASTRA</div>
  <div class="brand-tag">{_esc(labels["brand_tagline"])}</div>
  <div class="eyebrow" style="margin-top:44px">{_esc(labels["eyebrow"])}</div>
  <h1>{_esc(labels["persona_a"])} · {_esc(labels["persona_b"])}</h1>
  <div class="birth">{_esc(labels["birth_line"])}</div>
  {ruedas}
</div>
{seccion_aspectos}
{bloque_lectura}
<div class="footer"><span class="sol">☉</span> {_esc(labels["made_with"])}</div>
"""


class VinculoPdfView(_Base):
    """POST y no GET por lo mismo que el de la carta: el cuerpo trae la
    geometría de las ruedas, que calculó el navegador."""

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "pdf"

    def post(self, request, uuid):
        sujeto = self._vinculo(request, uuid)
        serializer = VinculoPdfSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning("pdf: payload rechazado para el vínculo %s", sujeto.uuid)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            pdf = render_html(
                build_vinculo_html(sujeto, serializer.validated_data), f"el vínculo {sujeto.uuid}",
            )
        except PdfGenerationError:
            return Response(
                {"error": "no se pudo generar el PDF"}, status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        labels = serializer.validated_data["labels"]
        ascii_name, utf8_name = pdf_filename(
            " - ".join(x for x in (labels["persona_a"], labels["persona_b"]) if x) or "vinculo"
        )
        respuesta = HttpResponse(pdf, content_type="application/pdf")
        respuesta["Content-Disposition"] = (
            f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}'
        )
        return respuesta

