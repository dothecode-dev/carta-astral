"""El contrato del PDF: qué le puede mandar el cliente al generador.

La decisión de fondo es que acá no entra markup. Entran números —la geometría que
`astra-wheel` ya calculó en el navegador— y texto ya traducido, porque el
diccionario de nombres vive en `web/lib/i18n.ts` y duplicarlo en Python sería una
tercera copia de la misma verdad.

Todo lo que no está declarado se rechaza: los campos desconocidos hacen fallar la
validación en vez de ignorarse, que es el default de DRF. Un payload que no se
entiende no se dibuja a medias.

`build()`, más abajo, es la excepción a ese contrato: no valida nada del
cliente, arma la parte de la lectura que el cliente NO manda —viaja sólo
`reading_lang`— a partir de lo que ya está persistido. Vive acá y no en
`chart_pdf_service` porque es la otra mitad del mismo contrato: qué forma
tiene el "payload" de lectura que consume el armado del HTML.
"""

from __future__ import annotations

import math
from typing import Any

from rest_framework import serializers

from api.informe_service import secciones_aplicables
from api.models import Chart, Interpretation


class _Number(serializers.FloatField):
    """Un número de verdad, no cualquier cosa que Python acepte como float.

    `float("NaN")` es un float válido y pasa `min_value`/`max_value` sin
    inmutarse —toda comparación con NaN da False—, así que llegaba entero al
    atributo del SVG. Infinity, igual.
    """

    def to_internal_value(self, data):
        valor = super().to_internal_value(data)
        if not math.isfinite(valor):
            self.fail("invalid")
        return valor


# El SVG mide unos cientos de unidades de lado; cualquier cosa fuera de este
# rango es basura o un intento de romper el layout, no una rueda.
def _coord(**extra):
    return _Number(min_value=-5000, max_value=5000, **extra)


class _Strict(serializers.Serializer):
    """Serializer que rechaza lo que no declaró."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("se esperaba un objeto")
        sobran = set(data) - set(self.fields)
        if sobran:
            raise serializers.ValidationError(
                {campo: "campo no reconocido" for campo in sorted(sobran)}
            )
        return super().to_internal_value(data)


class _Ring(_Strict):
    outer = _coord()
    signs = _coord()
    houses = _coord()
    aspect = _coord()


class _Sign(_Strict):
    glyph = serializers.CharField(max_length=8)
    x = _coord()
    y = _coord()


class _Cusp(_Strict):
    label = serializers.CharField(max_length=8)
    axis = serializers.BooleanField()
    x1 = _coord()
    y1 = _coord()
    x2 = _coord()
    y2 = _coord()
    label_x = _coord()
    label_y = _coord()


class _AspectLine(_Strict):
    # El color no viaja: viaja un tono de una lista cerrada, y el color lo pone
    # este backend. Así nada que venga de afuera se escribe como atributo del SVG.
    tone = serializers.ChoiceField(choices=["soft", "hard", "neutral"])
    x1 = _coord()
    y1 = _coord()
    x2 = _coord()
    y2 = _coord()


class _Angle(_Strict):
    label = serializers.CharField(max_length=8)
    x = _coord()
    y = _coord()


class _Body(_Strict):
    glyph = serializers.CharField(max_length=8)
    accent = serializers.BooleanField()
    x = _coord()
    y = _coord()
    tick_x1 = _coord()
    tick_y1 = _coord()
    tick_x2 = _coord()
    tick_y2 = _coord()
    leader_x1 = _coord()
    leader_y1 = _coord()
    leader_x2 = _coord()
    leader_y2 = _coord()


class _Wheel(_Strict):
    view_box = _Number(min_value=1, max_value=5000)
    center = _coord()
    rings = _Ring()
    signs = serializers.ListField(child=_Sign(), max_length=24)
    cusps = serializers.ListField(child=_Cusp(), max_length=24)
    aspect_lines = serializers.ListField(child=_AspectLine(), max_length=600)
    angles = serializers.ListField(child=_Angle(), max_length=8)
    bodies = serializers.ListField(child=_Body(), max_length=40)


class _Labels(_Strict):
    brand_tagline = serializers.CharField(max_length=240, allow_blank=True)
    eyebrow = serializers.CharField(max_length=240, allow_blank=True)
    chart_name = serializers.CharField(max_length=160, allow_blank=True)
    birth_line = serializers.CharField(max_length=240, allow_blank=True)
    positions = serializers.CharField(max_length=240, allow_blank=True)
    aspects = serializers.CharField(max_length=240, allow_blank=True)
    reading = serializers.CharField(max_length=240, allow_blank=True)
    made_with = serializers.CharField(max_length=240, allow_blank=True)


class _Position(_Strict):
    glyph = serializers.CharField(max_length=8, allow_blank=True)
    name = serializers.CharField(max_length=80)
    position = serializers.CharField(max_length=80, allow_blank=True)
    house = serializers.CharField(max_length=12, allow_blank=True)
    retrograde = serializers.BooleanField()


class _Aspect(_Strict):
    glyph = serializers.CharField(max_length=24, allow_blank=True)
    name = serializers.CharField(max_length=80)
    detail = serializers.CharField(max_length=60, allow_blank=True)


class _MatrixCell(_Strict):
    glyph = serializers.CharField(max_length=4)
    tone = serializers.ChoiceField(choices=["soft", "hard", "neutral"])


class _MatrixRow(_Strict):
    label = serializers.CharField(max_length=8)
    # Sólo el triángulo: la fila i trae i+1 celdas, y `None` donde no hay aspecto.
    cells = serializers.ListField(child=_MatrixCell(allow_null=True), max_length=24)


class _AspectMatrix(_Strict):
    """La matriz triangular, la misma que muestra la web.

    Llega armada por `buildMatrix` de `astra-wheel` —el mismo paquete que
    resuelve la rueda—, así que acá tampoco se decide qué va en cada cruce.
    """

    labels = serializers.ListField(child=serializers.CharField(max_length=8), max_length=24)
    rows = serializers.ListField(child=_MatrixRow(), max_length=24)


class ChartPdfSerializer(_Strict):
    labels = _Labels()
    positions = serializers.ListField(child=_Position(), max_length=80)
    aspects = serializers.ListField(child=_Aspect(), max_length=600)
    # Sin hora de nacimiento no hay Ascendente y la rueda no se puede orientar:
    # el documento sale con las tablas y sin rueda.
    wheel = _Wheel(required=False, allow_null=True)
    # Sin aspectos, o sin cuerpos que los tengan, no hay matriz que dibujar.
    aspect_matrix = _AspectMatrix(required=False, allow_null=True)
    # El idioma de la lectura a incluir. None es el caso normal: el PDF de la
    # carta sola. El texto NO viaja acá; lo lee el backend de su propia base.
    reading_lang = serializers.ChoiceField(
        choices=["es", "en", "pt"], required=False, allow_null=True
    )


def build(chart: Chart, interpretacion: Interpretation) -> dict[str, Any]:
    """La lectura para el PDF: título y texto de cada sección ya escrita, más
    el índice completo del informe.

    El índice sale de `secciones_aplicables(chart)` —el catálogo, filtrado
    por si hay hora de nacimiento—, no de `interpretacion.secciones.all()`:
    nombra las que corresponden aunque alguna todavía no se haya escrito
    (mismo criterio que `informe_service.resumen_gratis`). `secciones` en
    cambio sólo trae las que ya están: no hay texto que mostrar para una que
    falta.

    Quien llama decide si `interpretacion` corresponde a un informe
    terminado (`completa=True`); acá no se vuelve a chequear.

    Caso legacy: `0020_backfill_completa` preserva a propósito las filas de
    antes de la Tarea 2 —`completa=True`, `text` poblado, cero
    `InterpretationSection`—, y siguen existiendo en producción. Sin este
    caso, esas lecturas ya pagadas llegaban al PDF con la portada, el índice
    y el disclaimer de un informe terminado, y el cuerpo vacío: el texto
    desaparecía sin ningún error (hallazgo de revisión). Acá se detectan por
    "cero secciones y texto no vacío" y se sirven como una única pieza sin
    título de catálogo (`titulo=""`, que `chart_pdf_service` interpreta como
    "renderizar con el markdown liviano de antes", no con el título de una
    sección del catálogo que este texto nunca tuvo). El índice para este caso
    queda vacío a propósito: una lectura de una sola pieza no tiene ocho
    capítulos, y prometerlos sería mentir sobre una estructura que el texto
    no tiene.
    """
    aplicables = secciones_aplicables(chart)
    lang = interpretacion.lang
    escritas = {s.slug: s.texto for s in interpretacion.secciones.all()}

    if not escritas and interpretacion.text:
        secciones = [{"titulo": "", "texto": interpretacion.text}]
        indice: list[str] = []
    else:
        secciones = [
            {"titulo": seccion.titulo[lang], "texto": escritas[seccion.slug]}
            for seccion in aplicables
            if seccion.slug in escritas
        ]
        indice = [seccion.titulo[lang] for seccion in aplicables]

    return {"reading": {"secciones": secciones, "indice": indice}}
