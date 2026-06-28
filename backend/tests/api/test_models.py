import datetime
import pytest
from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db


def test_create_birthdata_and_chart():
    bd = BirthData.objects.create(
        name="Test", date=datetime.date(1989, 7, 14), time=datetime.time(23, 45),
        time_known=True, lat=-34.5, lng=-58.4, tz_name="America/Argentina/Buenos_Aires",
        datetime_utc=datetime.datetime(1989, 7, 15, 2, 45, tzinfo=datetime.timezone.utc),
    )
    chart = Chart.objects.create(
        birth_data=bd, house_system="Placidus", zodiac="Tropical",
        data={"placements": []}, engine_version="kerykeion 5.12.9",
    )
    assert chart.birth_data.name == "Test"
    assert chart.data == {"placements": []}
    assert chart.svg is None
