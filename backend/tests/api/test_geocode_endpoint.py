import pytest

from api.models import GeoName, GeoNameToken
from api.text_norm import tokenize

pytestmark = pytest.mark.django_db


def make_city(name, **kw):
    g = GeoName.objects.create(
        geonameid=kw.get("gid", 1),
        name=name,
        asciiname=name,
        lat=kw.get("lat", -34.6),
        lng=kw.get("lng", -58.4),
        country_code=kw.get("country", "AR"),
        admin1=kw.get("admin1", ""),
        population=kw.get("population", 1000),
    )
    for tok in tokenize(name):
        GeoNameToken.objects.create(geoname=g, token=tok)
    return g


def test_post_returns_candidates(account_client):
    make_city("Córdoba", population=1_430_023)
    resp = account_client.post("/api/geocode/", {"q": "cordoba"}, format="json")
    assert resp.status_code == 200
    assert resp.data["results"][0]["name"] == "Córdoba"
    keys = set(resp.data["results"][0])
    assert keys == {"place_query", "name", "lat", "lng", "tz_name", "country_code", "admin1", "population"}


def test_post_no_match_returns_empty_list(account_client):
    make_city("Córdoba")
    resp = account_client.post("/api/geocode/", {"q": "tokyo"}, format="json")
    assert resp.status_code == 200
    assert resp.data["results"] == []


def test_post_short_query_returns_400(account_client):
    resp = account_client.post("/api/geocode/", {"q": "a"}, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_post_missing_q_returns_400(account_client):
    resp = account_client.post("/api/geocode/", {}, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data
