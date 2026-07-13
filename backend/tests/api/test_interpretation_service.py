import datetime

import pytest
from django.core.cache import cache
from django.conf import settings as django_settings

from api import interpretation_service as svc
from api.models import Account, BirthData, Chart, Interpretation
from interpret.exceptions import InterpretationError

pytestmark = pytest.mark.django_db


def _account(free_balance=None, paid_balance=0):
    fb = django_settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
    return Account.objects.create(free_balance=fb, paid_balance=paid_balance)


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
    interp = svc.get_or_create_interpretation(c, "es", _account())
    assert interp.text == "una interpretación"
    assert Interpretation.objects.count() == 1
    assert fake_client.calls == 1


def test_hit_serves_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    acc = _account()
    svc.get_or_create_interpretation(c, "es", acc)
    svc.get_or_create_interpretation(c, "es", acc)
    assert fake_client.calls == 1
    assert Interpretation.objects.count() == 1


def test_daily_cap_blocks_new_generation(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    settings.INSTALL_FREE_CREDITS = 5  # both generations are free, to isolate the cap
    acc = _account()  # free_balance=5 (reads settings at call time)
    svc.get_or_create_interpretation(_chart(), "es", acc)
    with pytest.raises(svc.CapReached):
        # data distinto: si fuera idéntico, dedupearía en vez de llegar al cap
        svc.get_or_create_interpretation(
            _chart_with_data({"time_known": True, "utc_iso": "1990-01-01T00:00:00Z"}), "es", acc
        )
    assert fake_client.calls == 1


def test_cap_does_not_block_cache_hits(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    c = _chart()
    acc = _account()
    svc.get_or_create_interpretation(c, "es", acc)
    again = svc.get_or_create_interpretation(c, "es", acc)
    assert again.text == "una interpretación"
    assert fake_client.calls == 1


def test_lock_held_raises_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    cache.add(f"interp:lock:{c.id}:es:v1", "1", timeout=30)
    with pytest.raises(InterpretationError):
        svc.get_or_create_interpretation(c, "es", _account())
    assert fake_client.calls == 0


def _chart_with_data(data):
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data=data, engine_version="test")


def test_dedup_reuses_text_across_identical_charts_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z", "placements": [1, 2]}
    a = _chart_with_data(dict(data))
    b = _chart_with_data(dict(data))
    first = svc.get_or_create_interpretation(a, "es", _account())
    second = svc.get_or_create_interpretation(b, "es", _account())
    assert fake_client.calls == 1
    assert second.text == first.text
    assert Interpretation.objects.count() == 2  # cada carta conserva su fila


def test_dedup_still_charges_credit(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z"}
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", _account())
    acc = _account(free_balance=1)
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", acc)
    acc.refresh_from_db()
    assert svc.credits_available(acc) == 0


def test_dedup_requires_credit_even_with_donor(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z"}
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", _account())
    broke = _account(free_balance=0, paid_balance=0)
    with pytest.raises(svc.QuotaExceeded):
        svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", broke)
    assert Interpretation.objects.count() == 1


def test_dedup_does_not_consume_daily_cap(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    settings.INSTALL_FREE_CREDITS = 5
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z"}
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", _account())
    # hit de dedup: gratis en LLM, no debe contar contra el cap
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", _account())
    assert fake_client.calls == 1
    # una carta realmente distinta todavía entra (el cap solo contó 1 llamada real)
    with pytest.raises(svc.CapReached):
        svc.get_or_create_interpretation(
            _chart_with_data({"time_known": True, "utc_iso": "1990-01-01T00:00:00Z"}),
            "es",
            _account(),
        )


def test_different_data_or_lang_does_not_dedup(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z"}
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "es", _account())
    svc.get_or_create_interpretation(
        _chart_with_data({"time_known": True, "utc_iso": "1989-07-15T02:46:00Z"}), "es", _account()
    )
    svc.get_or_create_interpretation(_chart_with_data(dict(data)), "en", _account())
    assert fake_client.calls == 3


def test_llm_error_does_not_persist(monkeypatch, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _Boom())
    c = _chart()
    with pytest.raises(InterpretationError):
        svc.get_or_create_interpretation(c, "es", _account())
    assert Interpretation.objects.count() == 0
