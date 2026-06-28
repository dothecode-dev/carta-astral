import pytest
from rest_framework.test import APIClient
from api.chart_service import create_chart

pytestmark = pytest.mark.django_db


def test_post_creates_chart_returns_201():
    client = APIClient()
    resp = client.post("/api/charts/", {
        "name": "Test", "date": "1989-07-14", "time": "23:45",
        "time_known": True, "lat": -34.5, "lng": -58.4,
    }, format="json")
    assert resp.status_code == 201
    assert resp.data["id"]
    assert resp.data["data"]["placements"]


def test_get_returns_existing_chart():
    chart = create_chart({
        "date": "1990-01-01", "time": "00:00", "time_known": True,
        "lat": 51.5, "lng": -0.12,
    })
    client = APIClient()
    resp = client.get(f"/api/charts/{chart.id}/")
    assert resp.status_code == 200
    assert resp.data["id"] == chart.id


def test_get_missing_chart_returns_404():
    resp = APIClient().get("/api/charts/999999/")
    assert resp.status_code == 404
