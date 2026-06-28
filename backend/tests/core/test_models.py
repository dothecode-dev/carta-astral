import datetime
from core.models import BirthInput, Placement, ChartData, DegradationFlags


def test_birthinput_defaults():
    bi = BirthInput(
        name="Test", date=datetime.date(1989, 7, 14), time=datetime.time(23, 45),
        time_known=True, lat=-34.5, lng=-58.4,
    )
    assert bi.house_system == "Placidus"
    assert bi.zodiac == "Tropical"


def test_chartdata_holds_placements_and_flags():
    p = Placement(name="Sun", sign="Can", position=22.6, abs_pos=112.6, house="Fourth_House", retrograde=False)
    cd = ChartData(
        placements=[p], houses=None, angles=None, aspects=[],
        zodiac="Tropical", house_system="Placidus", time_known=False,
        flags=DegradationFlags(moon_approximate=True), julian_day=2447722.61, utc_iso="1989-07-15T02:45:00+00:00",
    )
    assert cd.placements[0].name == "Sun"
    assert cd.houses is None
    assert cd.flags.moon_approximate is True
