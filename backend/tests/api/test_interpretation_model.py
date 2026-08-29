import datetime

import pytest
from django.db import IntegrityError

from api.models import BirthData, Chart, Interpretation

pytestmark = pytest.mark.django_db


def _chart():
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"placements": []}, engine_version="test")


def test_interpretation_persists():
    c = _chart()
    interp = Interpretation.objects.create(chart=c, lang="es", prompt_version="v1", text="hola")
    assert interp.created_at is not None
    assert c.interpretations.count() == 1


def test_tier_default_es_largo():
    """Las filas que ya existen en producción (generadas antes de que existiera
    `tier`) son informes completos de ocho secciones, no lecturas breves. El
    default="largo" las etiqueta correctamente sin necesidad de backfill.
    Si alguien cambiera el default a "corto", toda la suite pasaría en verde
    pero las filas viejas se leerían como lecturas breves. Este test falla si
    eso sucede."""
    c = _chart()
    interp = Interpretation.objects.create(chart=c, lang="es", prompt_version="v1", text="hola")
    assert interp.tier == "largo"


def test_interpretation_unique_per_chart_lang_version():
    c = _chart()
    Interpretation.objects.create(chart=c, lang="es", prompt_version="v1", text="a")
    with pytest.raises(IntegrityError):
        Interpretation.objects.create(chart=c, lang="es", prompt_version="v1", text="b")


def test_corto_y_largo_conviven_en_la_misma_carta():
    """El upgrade (RF6) es el caso de negocio: leí la breve, pago, quiero el
    completo de ESA carta. Si el tier no está en la clave única, el segundo
    choca contra el unique y el usuario que pagó no puede generar."""
    chart = _chart()
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version="v2", tier="corto", text="breve",
    )
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version="v2", tier="largo", text="completo",
    )
    assert chart.interpretations.count() == 2


def test_no_se_duplica_el_mismo_tier():
    """La clave única incluye tier: el mismo tier sobre la misma carta falla.
    Protege contra generación duplicada del mismo producto: si dos requests
    concurrentes intentan generar la lectura breve de la misma carta, solo uno
    gana la carrera y cobra; el segundo recupera la fila existente."""
    chart = _chart()
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version="v2", tier="corto", text="a",
    )
    with pytest.raises(IntegrityError):
        Interpretation.objects.create(
            chart=chart, lang="es", prompt_version="v2", tier="corto", text="b",
        )
