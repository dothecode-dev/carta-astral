import datetime
import pytest
from core.timeconv import resolve_tz, resolve_dst, DstResolution
from core.exceptions import GeocodeTimezoneError


def test_resolve_tz_buenos_aires():
    assert resolve_tz(lat=-34.6, lng=-58.4) == "America/Argentina/Buenos_Aires"


def test_resolve_tz_open_ocean_raises():
    with pytest.raises(GeocodeTimezoneError):
        resolve_tz(lat=0.0, lng=-30.0)  # Atlántico medio, sin tz terrestre


def test_resolve_dst_normal_hour():
    r = resolve_dst(datetime.date(1989, 7, 14), datetime.time(23, 45), "America/Argentina/Buenos_Aires")
    assert r.ambiguous_resolved is False


def test_resolve_dst_ambiguous_fall_back():
    # US Eastern: 2021-11-07 01:30 ocurre dos veces (fin de DST)
    r = resolve_dst(datetime.date(2021, 11, 7), datetime.time(1, 30), "America/New_York")
    assert r.ambiguous_resolved is True
    assert r.is_dst is True  # primera ocurrencia = aún en DST


def test_resolve_dst_nonexistent_spring_forward():
    # US Eastern 2021-03-14 02:30 does not exist (clocks jump 02:00 -> 03:00)
    r = resolve_dst(datetime.date(2021, 3, 14), datetime.time(2, 30), "America/New_York")
    assert r.ambiguous_resolved is False
    assert r.is_dst is True  # adopt posterior offset (EDT)
