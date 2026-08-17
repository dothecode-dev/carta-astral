"""El contrato del PDF: qué le puede mandar el cliente al generador.

La decisión de fondo es que acá no entra markup. Entran números —la geometría que
`astra-wheel` ya calculó en el navegador— y texto ya traducido, porque el
diccionario de nombres vive en `web/lib/i18n.ts` y duplicarlo en Python sería una
tercera copia de la misma verdad.

Todo lo que no está declarado se rechaza: los campos desconocidos hacen fallar la
validación en vez de ignorarse, que es el default de DRF. Un payload que no se
entiende no se dibuja a medias.
"""

import math

from rest_framework import serializers


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


class ChartPdfSerializer(_Strict):
    labels = _Labels()
    positions = serializers.ListField(child=_Position(), max_length=80)
    aspects = serializers.ListField(child=_Aspect(), max_length=600)
    # Sin hora de nacimiento no hay Ascendente y la rueda no se puede orientar:
    # el documento sale con las tablas y sin rueda.
    wheel = _Wheel(required=False, allow_null=True)
    # El idioma de la lectura a incluir. None es el caso normal: el PDF de la
    # carta sola. El texto NO viaja acá; lo lee el backend de su propia base.
    reading_lang = serializers.ChoiceField(
        choices=["es", "en", "pt"], required=False, allow_null=True
    )
