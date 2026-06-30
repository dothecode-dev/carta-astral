import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from api.auth import create_session
from api.models import Account

PAYLOAD = {"date": "1990-05-20", "time": "10:30", "lat": -34.6, "lng": -58.4}


@pytest.mark.django_db
def test_chart_creation_throttled(monkeypatch):
    # Patch the class-level THROTTLE_RATES dict so each ScopedRateThrottle
    # instance reads "1/day" for the "chart" scope.  Overriding
    # settings.REST_FRAMEWORK alone is not enough because
    # SimpleRateThrottle.THROTTLE_RATES is assigned once at class-definition
    # time and does not re-read from settings on each request.
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"chart": "1/day"},
    )
    # Clear any stale throttle counters left by other tests.
    cache.clear()

    acc = Account.objects.create()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")

    first = c.post("/api/charts/", PAYLOAD, format="json")
    assert first.status_code == 201, f"expected 201, got {first.status_code}: {first.data}"

    second = c.post("/api/charts/", PAYLOAD, format="json")
    assert second.status_code == 429, f"expected 429, got {second.status_code}: {second.data}"


@pytest.mark.django_db
def test_chart_list_not_throttled_by_chart_scope(monkeypatch):
    # GET /api/charts/ must be unthrottled even when the POST cap is exhausted.
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"chart": "1/day"},
    )
    cache.clear()

    acc = Account.objects.create()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")

    # Exhaust the POST cap.
    assert c.post("/api/charts/", PAYLOAD, format="json").status_code == 201
    assert c.post("/api/charts/", PAYLOAD, format="json").status_code == 429

    # List should still succeed (get_throttles() returns [] for GET).
    get_resp = c.get("/api/charts/")
    assert get_resp.status_code == 200, f"GET unexpectedly blocked: {get_resp.status_code}"
