import uuid as uuidlib

import pytest

from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db


def _chart():
    bd = BirthData.objects.create(
        date="1989-07-14", time="23:45", time_known=True,
        lat=-34.5, lng=-58.4, tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"placements": []}, engine_version="test")


def test_chart_has_unique_uuid():
    a, b = _chart(), _chart()
    assert isinstance(a.uuid, uuidlib.UUID)
    assert a.uuid != b.uuid
