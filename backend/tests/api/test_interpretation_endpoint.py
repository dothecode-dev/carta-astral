import datetime
import uuid

import pytest
from django.core.cache import cache

from api import interpretation_service as svc
from api.models import BirthData, Chart, Interpretation

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _chart():
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"time_known": True}, engine_version="test")


class _Stream:
    def __init__(self, raises=None):
        self._raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._raises:
            raise self._raises

        class R:
            content = [type("B", (), {"type": "text", "text": "tu carta dice..."})()]
            stop_reason = "end_turn"

        return R()


class _FakeClient:
    class _M:
        def stream(self, **kw):
            return _Stream()

    @property
    def messages(self):
        return _FakeClient._M()


class _Boom:
    class _M:
        def stream(self, **kw):
            import anthropic

            return _Stream(raises=anthropic.AnthropicError("boom"))

    @property
    def messages(self):
        return _Boom._M()


@pytest.fixture
def fake_client(monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())


def test_post_returns_interpretation(auth_client, fake_client):
    c = _chart()
    resp = auth_client.post(f"/api/charts/{c.uuid}/interpretation/", {"lang": "es"}, format="json")
    assert resp.status_code == 200
    assert set(resp.data) == {"text", "lang", "prompt_version", "disclaimer", "created_at"}
    assert resp.data["text"] == "tu carta dice..."
    assert resp.data["disclaimer"] == svc.DISCLAIMERS["es"]


def test_default_lang_es(auth_client, fake_client):
    c = _chart()
    resp = auth_client.post(f"/api/charts/{c.uuid}/interpretation/", {}, format="json")
    assert resp.status_code == 200
    assert resp.data["lang"] == "es"


def test_invalid_lang_400(auth_client, fake_client):
    c = _chart()
    resp = auth_client.post(f"/api/charts/{c.uuid}/interpretation/", {"lang": "fr"}, format="json")
    assert resp.status_code == 400
    assert "error" in resp.data


def test_missing_chart_404(auth_client, fake_client):
    resp = auth_client.post(
        f"/api/charts/{uuid.uuid4()}/interpretation/", {"lang": "es"}, format="json"
    )
    assert resp.status_code == 404


def test_llm_error_503(auth_client, monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _Boom())
    c = _chart()
    resp = auth_client.post(f"/api/charts/{c.uuid}/interpretation/", {"lang": "es"}, format="json")
    assert resp.status_code == 503
    assert "error" in resp.data
    assert Interpretation.objects.count() == 0


def test_cap_reached_503(auth_client, monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 0
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())
    c = _chart()
    resp = auth_client.post(f"/api/charts/{c.uuid}/interpretation/", {"lang": "es"}, format="json")
    assert resp.status_code == 503
