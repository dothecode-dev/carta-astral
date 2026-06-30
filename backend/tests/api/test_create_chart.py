import pytest
from api.chart_service import create_chart
from api.models import Account, BirthData, Chart

pytestmark = pytest.mark.django_db


def test_create_chart_persists_birthdata_and_chart():
    acc = Account.objects.create()
    chart = create_chart({
        "name": "Test", "date": "1989-07-14", "time": "23:45",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    }, acc)
    assert Chart.objects.count() == 1
    assert BirthData.objects.count() == 1
    assert chart.birth_data.tz_name == "America/Argentina/Buenos_Aires"
    assert chart.data["placements"]  # non-empty
    assert "kerykeion" in chart.engine_version
    assert chart.birth_data.datetime_utc is not None


def test_create_chart_time_unknown_has_no_datetime_utc():
    acc = Account.objects.create()
    chart = create_chart({
        "date": "1989-07-14", "time": None, "time_known": False,
        "lat": -34.5, "lng": -58.4,
    }, acc)
    assert chart.birth_data.datetime_utc is None
    assert chart.birth_data.time_known is False
    assert chart.data["houses"] is None


def test_polar_chart_persists_whole_sign_fallback():
    # Tromsø, Norway (lat > 66, clearly on land so resolve_tz returns a real IANA zone)
    acc = Account.objects.create()
    chart = create_chart({
        "date": "1989-07-14", "time": "12:00", "time_known": True,
        "lat": 69.65, "lng": 18.96, "house_system": "Placidus",
    }, acc)
    assert chart.house_system == "Whole Sign"
    assert chart.data["flags"]["house_system_fallback"] is True
