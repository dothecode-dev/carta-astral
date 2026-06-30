import pytest

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
