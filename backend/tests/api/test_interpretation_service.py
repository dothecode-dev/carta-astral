import datetime

import pytest
from django.core.cache import cache

from api import interpretation_service as svc
from api.identity import new_token
from api.models import BirthData, Chart, Installation, Interpretation
from interpret.exceptions import InterpretationError

pytestmark = pytest.mark.django_db


def _inst():
    _, h = new_token()
    return Installation.objects.create(token_hash=h)


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
    def __init__(self, resp=None, raises=None):
        self._resp = resp
        self._raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._raises:
            raise self._raises

        class R:
            content = [type("B", (), {"type": "text", "text": "una interpretación"})()]
            stop_reason = "end_turn"

        return R()


class _FakeClient:
    calls = 0

    class _M:
        def stream(self, **kw):
            _FakeClient.calls += 1
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
def fake_client(monkeypatch):
    _FakeClient.calls = 0
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())
    return _FakeClient


def test_miss_generates_and_persists(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    interp = svc.get_or_create_interpretation(c, "es", _inst())
    assert interp.text == "una interpretación"
    assert Interpretation.objects.count() == 1
    assert fake_client.calls == 1


def test_hit_serves_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    inst = _inst()
    svc.get_or_create_interpretation(c, "es", inst)
    svc.get_or_create_interpretation(c, "es", inst)
    assert fake_client.calls == 1
    assert Interpretation.objects.count() == 1


def test_daily_cap_blocks_new_generation(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    inst = _inst()
    svc.get_or_create_interpretation(_chart(), "es", inst)
    with pytest.raises(svc.CapReached):
        svc.get_or_create_interpretation(_chart(), "es", inst)
    assert fake_client.calls == 1


def test_cap_does_not_block_cache_hits(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    c = _chart()
    inst = _inst()
    svc.get_or_create_interpretation(c, "es", inst)
    again = svc.get_or_create_interpretation(c, "es", inst)
    assert again.text == "una interpretación"
    assert fake_client.calls == 1


def test_lock_held_raises_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    cache.add(f"interp:lock:{c.id}:es:v1", "1", timeout=30)
    with pytest.raises(InterpretationError):
        svc.get_or_create_interpretation(c, "es", _inst())
    assert fake_client.calls == 0


def test_llm_error_does_not_persist(monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _Boom())
    c = _chart()
    with pytest.raises(InterpretationError):
        svc.get_or_create_interpretation(c, "es", _inst())
    assert Interpretation.objects.count() == 0
