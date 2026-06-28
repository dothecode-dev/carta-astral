from __future__ import annotations

import datetime
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from core.exceptions import GeocodeTimezoneError

_tf = TimezoneFinder()


def resolve_tz(lat: float, lng: float) -> str:
    tz = _tf.timezone_at(lat=lat, lng=lng)
    if tz is None or tz.startswith("Etc/"):
        raise GeocodeTimezoneError(f"sin timezone terrestre para lat={lat}, lng={lng}")
    return tz


@dataclass(frozen=True)
class DstResolution:
    is_dst: bool | None
    ambiguous_resolved: bool


def resolve_dst(date: datetime.date, time: datetime.time, tz_str: str) -> DstResolution:
    tz = ZoneInfo(tz_str)
    naive = datetime.datetime.combine(date, time)
    dt0 = naive.replace(tzinfo=tz, fold=0)
    dt1 = naive.replace(tzinfo=tz, fold=1)
    off0 = dt0.utcoffset()
    off1 = dt1.utcoffset()
    if off0 != off1:
        # hora ambigua: existe en dos offsets. Elegimos la primera ocurrencia (fold=0).
        # is_dst = True si fold=0 corresponde al offset DST (dst() distinto de cero).
        is_dst = dt0.dst() != datetime.timedelta(0)
        return DstResolution(is_dst=is_dst, ambiguous_resolved=True)
    return DstResolution(is_dst=None, ambiguous_resolved=False)
