import datetime
import pytest
from api.chart_service import create_chart
from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db


def test_create_chart_persists_birthdata_and_chart():
    chart = create_chart({
        "name": "Test", "date": "1989-07-14", "time": "23:45",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    })
    assert Chart.objects.count() == 1
    assert BirthData.objects.count() == 1
    assert chart.birth_data.tz_name == "America/Argentina/Buenos_Aires"
    assert chart.data["placements"]  # non-empty
    assert "kerykeion" in chart.engine_version
    assert chart.birth_data.datetime_utc is not None
