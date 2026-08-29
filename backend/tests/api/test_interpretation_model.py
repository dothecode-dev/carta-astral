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
    chart = _chart()
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version="v2", tier="corto", text="a",
    )
    with pytest.raises(IntegrityError):
        Interpretation.objects.create(
            chart=chart, lang="es", prompt_version="v2", tier="corto", text="b",
        )
