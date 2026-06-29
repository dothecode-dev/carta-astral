import pytest

from api.geocode import search
from api.models import GeoName, GeoNameToken
from api.text_norm import tokenize

pytestmark = pytest.mark.django_db


def make_city(name, *, country="AR", admin1="", population=0, lat=-34.6, lng=-58.4, gid=None):
    g = GeoName.objects.create(
        geonameid=gid if gid is not None else 10_000_000 + GeoName.objects.count(),
        name=name,
        asciiname=name,
        lat=lat,
        lng=lng,
        country_code=country,
        admin1=admin1,
        population=population,
    )
    for tok in tokenize(name):
        GeoNameToken.objects.create(geoname=g, token=tok)
    return g


def test_finds_city_by_exact_name():
    make_city("Córdoba", country="AR", population=1_430_023)
    results = search("cordoba")
    assert len(results) == 1
    assert results[0]["name"] == "Córdoba"


def test_finds_compound_name_by_inner_word():
    # El defecto que el critique marcó: prefijo sobre nombre completo no lo encontraba.
    make_city("San Carlos de Bariloche", population=108_205)
    results = search("bariloche")
    assert [r["name"] for r in results] == ["San Carlos de Bariloche"]


def test_multi_token_requires_all_tokens():
    make_city("San Juan", population=500_000)
    make_city("San Luis", population=200_000)
    make_city("Villa Carlos Paz", population=60_000)
    results = search("san juan")
    assert [r["name"] for r in results] == ["San Juan"]


def test_results_ranked_by_population_desc():
    make_city("Córdoba", country="ES", population=325_000)
    make_city("Córdoba", country="AR", population=1_430_023)
    results = search("cordoba")
    assert [r["country_code"] for r in results] == ["AR", "ES"]


def test_accent_insensitive_query():
    make_city("Córdoba", country="AR", population=1_430_023)
    assert search("Córdoba")[0]["name"] == "Córdoba"
    assert search("CORDOBA")[0]["name"] == "Córdoba"


def test_last_token_is_prefix_for_autocomplete():
    make_city("Bariloche", population=100_000)
    assert search("baril")[0]["name"] == "Bariloche"


def test_query_too_short_raises():
    with pytest.raises(ValueError):
        search("a")


def test_no_match_returns_empty():
    make_city("Córdoba", population=1_000)
    assert search("tokyo") == []


def test_respects_limit():
    for i in range(15):
        make_city("Santa Ciudad", population=i, gid=9_000_000 + i)
    assert len(search("santa", limit=10)) == 10


def test_candidate_has_display_fields():
    make_city("Córdoba", country="AR", admin1="Cordoba", population=1_430_023)
    cand = search("cordoba")[0]
    assert cand["place_query"].startswith("Córdoba")
    assert cand["place_query"].endswith("AR")
    assert cand["country_code"] == "AR"
    assert cand["admin1"] == "Cordoba"
    assert cand["lat"] == -34.6
    assert cand["population"] == 1_430_023
