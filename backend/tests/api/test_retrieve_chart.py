import uuid

import pytest

from api.chart_service import create_chart

pytestmark = pytest.mark.django_db


def test_post_creates_chart_returns_201(account_client):
    resp = account_client.post("/api/charts/", {
        "name": "Test", "date": "1989-07-14", "time": "23:45",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["id"]
    assert resp.data["data"]["placements"]
    assert resp.data["house_system"]
    assert resp.data["zodiac"]
    assert "kerykeion" in resp.data["engine_version"]


def test_get_returns_existing_chart(account_client):
    chart = create_chart({
        "date": "1990-01-01", "time": "00:00", "time_known": True,
        "lat": 51.5, "lng": -0.12,
    }, account=account_client.account)
    resp = account_client.get(f"/api/charts/{chart.uuid}/")
    assert resp.status_code == 200
    assert resp.data["id"] == str(chart.uuid)


def test_get_missing_chart_returns_404(account_client):
    resp = account_client.get(f"/api/charts/{uuid.uuid4()}/")
    assert resp.status_code == 404


def test_chart_repr_includes_birth_block(account_client):
    resp = account_client.post("/api/charts/", {
        "name": "Ceci", "date": "1976-05-31", "time": "19:30",
        "time_known": True, "lat": -34.516, "lng": -58.5,
        "place_label": "Florida, Buenos Aires, AR",
    }, format="json")
    assert resp.status_code == 201
    birth = resp.json()["birth"]
    assert birth == {
        "name": "Ceci",
        "date": "1976-05-31",
        "time": "19:30",
        "time_known": True,
        "lat": -34.516,
        "lng": -58.5,
        "tz_name": "America/Argentina/Buenos_Aires",
        "place_label": "Florida, Buenos Aires, AR",
    }


def test_chart_repr_lists_interpretation_langs(account_client):
    from api.models import Chart, Interpretation
    from interpret.prompts import PROMPT_VERSION

    resp = account_client.post("/api/charts/", {
        "name": "L", "date": "1990-01-01", "time": "12:00",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    }, format="json")
    assert resp.json()["interpretation_langs"] == []
    chart = Chart.objects.get(uuid=resp.json()["id"])
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="x", content_key="k",
    )
    detail = account_client.get(f"/api/charts/{chart.uuid}/")
    assert detail.json()["interpretation_langs"] == ["es"]
