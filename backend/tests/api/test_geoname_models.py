import pytest

from api.models import GeoName, GeoNameToken

pytestmark = pytest.mark.django_db


def test_geoname_persists_and_relates_tokens():
    g = GeoName.objects.create(
        geonameid=3838583,
        name="San Carlos de Bariloche",
        asciiname="San Carlos de Bariloche",
        lat=-41.13345,
        lng=-71.30979,
        country_code="AR",
        admin1_code="17",
        admin1="Rio Negro",
        tz_geonames="America/Argentina/Salta",
        population=108205,
    )
    for tok in ("san", "carlos", "de", "bariloche"):
        GeoNameToken.objects.create(geoname=g, token=tok)

    assert g.tokens.count() == 4
    assert GeoNameToken.objects.filter(token="bariloche").get().geoname == g
