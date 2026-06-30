import uuid

import pytest

from api.chart_service import create_chart

pytestmark = pytest.mark.django_db


def test_post_creates_chart_returns_201(auth_client):
    resp = auth_client.post("/api/charts/", {
        "name": "Test", "date": "1989-07-14", "time": "23:45",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["id"]
    assert resp.data["data"]["placements"]
    assert resp.data["house_system"]
    assert resp.data["zodiac"]
    assert "kerykeion" in resp.data["engine_version"]


def test_get_returns_existing_chart(auth_client):
    chart = create_chart({
        "date": "1990-01-01", "time": "00:00", "time_known": True,
        "lat": 51.5, "lng": -0.12,
    })
    resp = auth_client.get(f"/api/charts/{chart.uuid}/")
    assert resp.status_code == 200
    assert resp.data["id"] == str(chart.uuid)


def test_get_missing_chart_returns_404(auth_client):
    resp = auth_client.get(f"/api/charts/{uuid.uuid4()}/")
    assert resp.status_code == 404
