import pytest
from django.core.cache import cache
from django.utils import timezone

from api import interpretation_service as svc
from api.identity import new_token
from api.interpretation_service import (
    QuotaExceeded,
    credits_available,
    get_or_create_interpretation,
)
from api.models import BirthData, Chart, Installation

pytestmark = pytest.mark.django_db


def _inst():
    _, h = new_token()
    return Installation.objects.create(token_hash=h)


def _chart():
    bd = BirthData.objects.create(
        date="1989-07-14", time="23:45", time_known=True,
        lat=-34.5, lng=-58.4, tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"placements": []}, engine_version="test")


def test_available_starts_at_free_credits(settings):
    settings.INSTALL_FREE_CREDITS = 3
    assert credits_available(_inst()) == 3


def test_quota_exceeded_blocks_new_generation(settings, monkeypatch):
    settings.INSTALL_FREE_CREDITS = 0
    inst = _inst()
    with pytest.raises(QuotaExceeded):
        get_or_create_interpretation(_chart(), "es", inst)


def test_cache_hit_served_with_zero_credits(settings):
    settings.INSTALL_FREE_CREDITS = 0
    inst = _inst()
    chart = _chart()
    from api.models import Interpretation
    from interpret.prompts import PROMPT_VERSION
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="cached", installation=inst
    )
    # 0 créditos pero ya existe: se sirve sin error
    out = get_or_create_interpretation(chart, "es", inst)
    assert out.text == "cached"


def test_paid_generation_bypasses_daily_cap(settings, monkeypatch):
    """RF9: a paid generation bypasses the global daily cap and does not increment it."""
    from api.models import Interpretation

    settings.INSTALL_FREE_CREDITS = 0       # every generation is paid (used >= 0 == free_credits)
    settings.INTERPRETATION_DAILY_CAP = 0   # cap is at its limit for free generations

    _, h = new_token()
    inst = Installation.objects.create(token_hash=h, purchased_credits=5)
    chart = _chart()

    class _Stream:
        def __enter__(self): return self
        def __exit__(self, *exc): return False
        def get_final_message(self):
            class R:
                content = [type("B", (), {"type": "text", "text": "paid interp"})()]
                stop_reason = "end_turn"
            return R()

    class _FakeClient:
        class _M:
            def stream(self, **kw): return _Stream()
        @property
        def messages(self): return _FakeClient._M()

    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())

    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    cache.clear()

    before = cache.get(cap_key)
    interp = get_or_create_interpretation(chart, "es", inst)
    after = cache.get(cap_key)

    assert isinstance(interp, Interpretation)
    assert before is None
    assert after is None  # paid generation never touches the cap counter
