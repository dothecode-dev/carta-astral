from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass(frozen=True)
class BirthInput:
    name: str | None
    date: datetime.date
    time: datetime.time | None
    time_known: bool
    lat: float
    lng: float
    house_system: str = "Placidus"
    zodiac: str = "Tropical"


@dataclass(frozen=True)
class Placement:
    name: str
    sign: str
    position: float
    abs_pos: float
    house: str | None
    retrograde: bool


@dataclass(frozen=True)
class House:
    name: str
    sign: str
    abs_pos: float


@dataclass(frozen=True)
class Angle:
    name: str
    sign: str
    abs_pos: float


@dataclass(frozen=True)
class Aspect:
    p1: str
    p2: str
    aspect: str
    orbit: float
    movement: str


@dataclass(frozen=True)
class DegradationFlags:
    house_system_fallback: bool = False
    moon_approximate: bool = False
    precision_degraded: bool = False
    dst_ambiguous_resolved: bool = False


@dataclass(frozen=True)
class ChartData:
    placements: list[Placement]
    houses: list[House] | None
    angles: list[Angle] | None
    aspects: list[Aspect]
    zodiac: str
    house_system: str
    time_known: bool
    flags: DegradationFlags
    julian_day: float
    utc_iso: str
