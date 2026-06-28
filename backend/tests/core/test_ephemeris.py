import datetime
import pytest
from core.models import BirthInput
from core.ephemeris import build_chart


@pytest.fixture
def olivos() -> BirthInput:
    return BirthInput(
        name="Test", date=datetime.date(1989, 7, 14), time=datetime.time(23, 45),
        time_known=True, lat=-34.5, lng=-58.4,
    )


def test_build_chart_sun_position(olivos):
    cd = build_chart(olivos)
    sun = next(p for p in cd.placements if p.name == "Sun")
    assert sun.sign == "Can"
    assert sun.abs_pos == pytest.approx(112.606, abs=1e-2)
    assert sun.house == "Fourth_House"


def test_build_chart_has_houses_and_angles_when_time_known(olivos):
    cd = build_chart(olivos)
    assert cd.houses is not None and len(cd.houses) == 12
    assert cd.angles is not None
    asc = next(a for a in cd.angles if a.name == "Ascendant")
    assert asc.abs_pos == pytest.approx(4.860, abs=1e-2)
    assert cd.julian_day == pytest.approx(2447722.6146, abs=1e-3)


def test_time_unknown_omits_houses_and_angles():
    bi = BirthInput(
        name="NoTime", date=datetime.date(1989, 7, 14), time=None,
        time_known=False, lat=-34.5, lng=-58.4,
    )
    cd = build_chart(bi)
    assert cd.houses is None
    assert cd.angles is None
    assert cd.time_known is False
    assert cd.flags.moon_approximate is True
    assert all(p.house is None for p in cd.placements)
    # el Sol igual se calcula
    assert any(p.name == "Sun" for p in cd.placements)


def test_polar_latitude_falls_back_to_whole_sign():
    bi = BirthInput(
        name="Polar", date=datetime.date(1989, 7, 14), time=datetime.time(12, 0),
        time_known=True, lat=78.0, lng=15.0, house_system="Placidus",
    )
    cd = build_chart(bi)
    assert cd.flags.house_system_fallback is True
    assert cd.house_system == "Whole Sign"
