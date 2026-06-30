import pytest
from django.core.cache import cache
from django.utils import timezone

from api import interpretation_service as svc
from api.interpretation_service import (
    QuotaExceeded,
    credits_available,
    get_or_create_interpretation,
)
from api.models import Account, BirthData, Chart, Interpretation

pytestmark = pytest.mark.django_db


def _account(free_balance=None, paid_balance=0):
    from django.conf import settings
    fb = settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
    return Account.objects.create(free_balance=fb, paid_balance=paid_balance)


def _chart():
    bd = BirthData.objects.create(
        date="1989-07-14", time="23:45", time_known=True,
        lat=-34.5, lng=-58.4, tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"placements": []}, engine_version="test")


def test_available_starts_at_free_credits(settings):
    settings.INSTALL_FREE_CREDITS = 3
    assert credits_available(_account()) == 3


def test_quota_exceeded_blocks_new_generation(settings):
    settings.INSTALL_FREE_CREDITS = 0
    acc = _account()  # free_balance=0, paid_balance=0
    with pytest.raises(QuotaExceeded):
        get_or_create_interpretation(_chart(), "es", acc)


def test_cache_hit_served_with_zero_credits(settings):
    settings.INSTALL_FREE_CREDITS = 0
    acc = _account()  # free_balance=0, paid_balance=0
    chart = _chart()
    from interpret.prompts import PROMPT_VERSION
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="cached", account=acc
    )
    # 0 créditos pero ya existe: se sirve sin error
    out = get_or_create_interpretation(chart, "es", acc)
    assert out.text == "cached"


def test_paid_generation_bypasses_daily_cap(monkeypatch, settings):
    """RF9: a paid generation bypasses the global daily cap and does not increment it."""
    settings.INSTALL_FREE_CREDITS = 0
    settings.INTERPRETATION_DAILY_CAP = 0  # cap at its limit for free generations

    acc = Account.objects.create(free_balance=0, paid_balance=1)
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
    interp = get_or_create_interpretation(chart, "es", acc)
    after = cache.get(cap_key)

    assert isinstance(interp, Interpretation)
    assert before is None
    assert after is None  # paid generation never touches the cap counter
