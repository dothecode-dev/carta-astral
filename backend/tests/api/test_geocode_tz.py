from unittest.mock import patch

import pytest

from api.geocode import search
from api.models import GeoName, GeoNameToken
from api.text_norm import tokenize

pytestmark = pytest.mark.django_db


def make_city(name, *, lat, lng, tz_geonames="", gid=1):
    g = GeoName.objects.create(
        geonameid=gid,
        name=name,
        asciiname=name,
        lat=lat,
        lng=lng,
        country_code="AR",
        tz_geonames=tz_geonames,
        population=1000,
    )
    for tok in tokenize(name):
        GeoNameToken.objects.create(geoname=g, token=tok)
    return g


def test_tz_name_comes_from_core_resolve_tz():
    # Misma fuente que /api/charts/: timezonefinder desde lat/lng.
    make_city("Buenos Aires", lat=-34.6, lng=-58.4)
    cand = search("buenos aires")[0]
    assert cand["tz_name"] == "America/Argentina/Buenos_Aires"


def test_tz_falls_back_to_geonames_when_core_cannot_resolve():
    make_city("Isla Rara", lat=0.0, lng=0.0, tz_geonames="Etc/GMT")
    with patch("api.geocode.resolve_tz", side_effect=_raise_geocode_error):
        cand = search("isla rara")[0]
    assert cand["tz_name"] == "Etc/GMT"


def test_tz_is_none_when_core_fails_and_no_fallback():
    make_city("Isla Rara", lat=0.0, lng=0.0, tz_geonames="")
    with patch("api.geocode.resolve_tz", side_effect=_raise_geocode_error):
        cand = search("isla rara")[0]
    assert cand["tz_name"] is None


def _raise_geocode_error(*args, **kwargs):
    from core.exceptions import GeocodeTimezoneError

    raise GeocodeTimezoneError("sin timezone terrestre")
