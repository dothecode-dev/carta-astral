from __future__ import annotations

from timezonefinder import TimezoneFinder

from core.exceptions import GeocodeTimezoneError

_tf = TimezoneFinder()


def resolve_tz(lat: float, lng: float) -> str:
    tz = _tf.timezone_at(lat=lat, lng=lng)
    if tz is None or tz.startswith("Etc/"):
        raise GeocodeTimezoneError(f"sin timezone terrestre para lat={lat}, lng={lng}")
    return tz
