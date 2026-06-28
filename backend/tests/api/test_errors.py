import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_missing_required_field_returns_400():
    resp = APIClient().post("/api/charts/", {"date": "1989-07-14"}, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_ocean_coords_return_400():
    resp = APIClient().post("/api/charts/", {
        "date": "1989-07-14", "time": "12:00", "time_known": True,
        "lat": 0.0, "lng": -30.0,
    }, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data
