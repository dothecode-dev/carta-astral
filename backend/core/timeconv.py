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


def _is_dst(dt: datetime.datetime) -> bool:
    d = dt.dst()
    return d is not None and d != datetime.timedelta(0)


def resolve_dst(date: datetime.date, time: datetime.time, tz_str: str) -> DstResolution:
    tz = ZoneInfo(tz_str)
    naive = datetime.datetime.combine(date, time)
    dt0 = naive.replace(tzinfo=tz, fold=0)
    dt1 = naive.replace(tzinfo=tz, fold=1)
    off0 = dt0.utcoffset()
    off1 = dt1.utcoffset()
    if off0 == off1:
        # hora normal: un único offset. kerykeion infiere DST.
        return DstResolution(is_dst=None, ambiguous_resolved=False)
    assert off0 is not None and off1 is not None
    if off0 > off1:
        # fall-back: hora ambigua (ocurre dos veces). Elegimos la primera
        # ocurrencia (fold=0), que aún está en el offset DST que termina.
        return DstResolution(is_dst=_is_dst(dt0), ambiguous_resolved=True)
    # off0 < off1: spring-forward, hora inexistente. Adoptamos el offset
    # posterior al salto (fold=1). No fue ambigua, sino que no existió.
    return DstResolution(is_dst=_is_dst(dt1), ambiguous_resolved=False)
