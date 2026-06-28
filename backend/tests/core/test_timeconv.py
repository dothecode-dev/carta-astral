import pytest
from core.timeconv import resolve_tz
from core.exceptions import GeocodeTimezoneError


def test_resolve_tz_buenos_aires():
    assert resolve_tz(lat=-34.6, lng=-58.4) == "America/Argentina/Buenos_Aires"


def test_resolve_tz_open_ocean_raises():
    with pytest.raises(GeocodeTimezoneError):
        resolve_tz(lat=0.0, lng=-30.0)  # Atlántico medio, sin tz terrestre
