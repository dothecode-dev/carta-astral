import pytest
from rest_framework.test import APIClient
from api.auth import create_session
from api.models import Account


def _client(acc):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    return c


PAYLOAD = {"date": "1990-05-20", "time": "10:30", "lat": -34.6, "lng": -58.4}


@pytest.mark.django_db
def test_interpretation_scoped_to_account(monkeypatch, settings):
    """Account B cannot interpret account A's chart — must get 404 (multi-tenancy isolation)."""
    import api.interpretation_service as svc

    settings.INTERPRETATION_DAILY_CAP = 100
    # Prevent actual LLM call; if the scoping bug exists B would reach this and get 200.
    monkeypatch.setattr(svc, "build_interpretation", lambda *a, **kw: "fake text")

    a = Account.objects.create()
    b = Account.objects.create()

    # A creates a chart (chart.account = a)
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert resp.status_code == 201
    a_uuid = resp.data["id"]

    # B tries to interpret A's chart — must be 404, not a cross-account read
    resp = _client(b).post(
        f"/api/charts/{a_uuid}/interpretation/",
        {"lang": "es"},
        format="json",
    )
    assert resp.status_code == 404


@pytest.mark.django_db
def test_chart_visible_only_to_owner():
    a = Account.objects.create()
    b = Account.objects.create()
    resp = _client(a).post("/api/charts/", PAYLOAD, format="json")
    assert resp.status_code == 201
    uuid = resp.data["id"]
    assert _client(a).get(f"/api/charts/{uuid}/").status_code == 200
    assert _client(b).get(f"/api/charts/{uuid}/").status_code == 404


@pytest.mark.django_db
def test_chart_list_scoped_to_account():
    a = Account.objects.create()
    _client(a).post("/api/charts/", PAYLOAD, format="json")
    resp = _client(a).get("/api/charts/")
    assert resp.status_code == 200
    assert len(resp.data["results"]) == 1
    # otra cuenta no ve nada
    b = Account.objects.create()
    assert len(_client(b).get("/api/charts/").data["results"]) == 0
    # cross-exclusion: B creates its own chart; A still sees only 1, B sees only 1
    _client(b).post("/api/charts/", PAYLOAD, format="json")
    assert len(_client(a).get("/api/charts/").data["results"]) == 1
    assert len(_client(b).get("/api/charts/").data["results"]) == 1
