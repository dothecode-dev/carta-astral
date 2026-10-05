"""La Luna de un instante: fase, próximas fases y próximo cambio de signo.

Las fases las calcula kerykeion (`MoonPhaseDetailsFactory`), que busca con
Swiss Ephemeris el instante exacto en que el ángulo Sol-Luna llega a 0°, 90°,
180° y 270°: coincide al minuto con el U.S. Naval Observatory. Lo que kerykeion
no da es cuándo la Luna cambia de signo; eso sale de `swe.mooncross_ut`, que
busca el cruce de una longitud con la misma efeméride que dibuja las cartas.
"""

from __future__ import annotations

from datetime import datetime, timezone

import swisseph as swe
from kerykeion import AstrologicalSubjectFactory
from kerykeion.moon_phase_details.factory import MoonPhaseDetailsFactory
from kerykeion.moon_phase_details.utils import configure_ephemeris_path
from kerykeion.utilities import datetime_to_julian, julian_to_datetime

from core.models import MoonState, PhaseEvent, SignChange

# Las abreviaturas de kerykeion, las mismas que devuelve `sky_now`.
_SIGNS = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir",
          "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis")

_MAJOR_PHASES = ("new_moon", "first_quarter", "full_moon", "last_quarter")


def _snake(name: str) -> str:
    """"Waning Gibbous" → "waning_gibbous"."""
    return name.strip().lower().replace(" ", "_")


def _next_sign_change(moment: datetime) -> SignChange:
    configure_ephemeris_path()
    jd = datetime_to_julian(moment)
    moon_lon = float(swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)[0][0])
    index = (int(moon_lon // 30) + 1) % 12
    crossing = swe.mooncross_ut(index * 30.0, jd, swe.FLG_SWIEPH)
    when = julian_to_datetime(crossing).replace(tzinfo=timezone.utc)
    return SignChange(sign=_SIGNS[index], moment=when)


def moon_state(moment: datetime) -> MoonState:
    """La Luna en `moment`, que tiene que traer zona horaria."""
    if moment.tzinfo is None:
        raise ValueError("moon_state necesita un datetime con zona horaria")
    utc = moment.astimezone(timezone.utc)

    subject = AstrologicalSubjectFactory.from_birth_data(
        "Sky", utc.year, utc.month, utc.day, utc.hour, utc.minute,
        lng=0.0, lat=0.0, tz_str="UTC", online=False,
    )
    moon = MoonPhaseDetailsFactory.from_subject(subject).moon

    upcoming = moon.detailed.upcoming_phases if moon.detailed else None
    if upcoming is None:
        raise RuntimeError("kerykeion no devolvió las próximas fases")
    events = []
    for phase in _MAJOR_PHASES:
        window = getattr(upcoming, phase)
        if window is None or window.next is None or window.next.timestamp is None:
            raise RuntimeError(f"kerykeion no encontró la próxima {phase}")
        when = datetime.fromtimestamp(window.next.timestamp, tz=timezone.utc)
        events.append(PhaseEvent(phase=phase, moment=when))
    events.sort(key=lambda e: e.moment)

    if moon.phase_name is None:
        raise RuntimeError("kerykeion no devolvió el nombre de la fase")
    illumination = int(str(moon.illumination).rstrip("%"))
    sign = moon.zodiac.moon_sign if moon.zodiac else ""

    return MoonState(
        sign=sign,
        phase=_snake(moon.phase_name),
        illumination=illumination,
        waxing=moon.stage == "waxing",
        next_phases=events,
        next_sign_change=_next_sign_change(utc),
    )
