from __future__ import annotations

from typing import Literal, cast

from kerykeion import AstrologicalSubject

from core.models import Angle, ChartData, DegradationFlags, House, Placement, BirthInput
from core.timeconv import resolve_dst, resolve_tz

# espeja el enum interno de kerykeion; sólo usamos los 5 de _HOUSE_CODE
_HouseLiteral = Literal[
    "A", "B", "C", "D", "F", "H", "I", "i", "K", "L", "M",
    "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y",
]

_HOUSE_CODE = {"Placidus": "P", "Whole Sign": "W", "Koch": "K", "Porphyry": "O", "Equal": "A"}
_PLANET_ATTRS = ["sun", "moon", "mercury", "venus", "mars", "jupiter", "saturn",
                 "uranus", "neptune", "pluto", "chiron", "true_north_lunar_node"]
_HOUSE_ATTRS = ["first_house", "second_house", "third_house", "fourth_house",
                "fifth_house", "sixth_house", "seventh_house", "eighth_house",
                "ninth_house", "tenth_house", "eleventh_house", "twelfth_house"]
_ANGLE_ATTRS = ["ascendant", "medium_coeli", "descendant", "imum_coeli"]


def build_chart(birth: BirthInput) -> ChartData:
    if not birth.time_known or birth.time is None:
        subj = AstrologicalSubject(
            name=birth.name or "Chart",
            year=birth.date.year, month=birth.date.month, day=birth.date.day,
            hour=12, minute=0, lng=birth.lng, lat=birth.lat, tz_str="UTC", online=False,
            zodiac_type=("Sidereal" if birth.zodiac == "Sidereal" else "Tropical"),
        )
        model = subj.model()
        placements = [
            Placement(name=p.name, sign=p.sign, position=p.position, abs_pos=p.abs_pos,
                      house=None, retrograde=bool(getattr(p, "retrograde", False)))
            for p in (getattr(model, a) for a in _PLANET_ATTRS)
        ]
        return ChartData(
            placements=placements, houses=None, angles=None, aspects=[],
            zodiac=birth.zodiac, house_system=birth.house_system, time_known=False,
            flags=DegradationFlags(moon_approximate=True),
            julian_day=model.julian_day, utc_iso=model.iso_formatted_utc_datetime,
        )

    fallback = False
    house_system = birth.house_system
    if abs(birth.lat) > 66 and house_system in ("Placidus", "Koch", "Porphyry"):
        house_system = "Whole Sign"
        fallback = True

    try:
        house_code = _HOUSE_CODE[house_system]
    except KeyError:
        raise ValueError(f"house_system no soportado: {birth.house_system!r}") from None

    tz_str = resolve_tz(birth.lat, birth.lng)
    dst = resolve_dst(birth.date, birth.time, tz_str)

    subj = AstrologicalSubject(
        name=birth.name or "Chart",
        year=birth.date.year, month=birth.date.month, day=birth.date.day,
        hour=birth.time.hour, minute=birth.time.minute,
        lng=birth.lng, lat=birth.lat, tz_str=tz_str, online=False,
        houses_system_identifier=cast(_HouseLiteral, house_code),
        zodiac_type=("Sidereal" if birth.zodiac == "Sidereal" else "Tropical"),
        is_dst=dst.is_dst,
    )
    model = subj.model()

    placements = [
        Placement(name=p.name, sign=p.sign, position=p.position, abs_pos=p.abs_pos,
                  house=p.house, retrograde=bool(getattr(p, "retrograde", False)))
        for p in (getattr(model, a) for a in _PLANET_ATTRS)
    ]
    houses = [House(name=h.name, sign=h.sign, abs_pos=h.abs_pos)
              for h in (getattr(model, a) for a in _HOUSE_ATTRS)]
    angles = [Angle(name=g.name, sign=g.sign, abs_pos=g.abs_pos)
              for g in (getattr(model, a) for a in _ANGLE_ATTRS)]

    return ChartData(
        placements=placements, houses=houses, angles=angles, aspects=[],
        zodiac=birth.zodiac, house_system=house_system, time_known=True,
        flags=DegradationFlags(dst_ambiguous_resolved=dst.ambiguous_resolved,
                               house_system_fallback=fallback),
        julian_day=model.julian_day, utc_iso=model.iso_formatted_utc_datetime,
    )
