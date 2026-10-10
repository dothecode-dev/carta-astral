"""La Luna de un instante: fase, próximas fases y próximo cambio de signo.

El nombre de la fase y la iluminación los da kerykeion. Los instantes salen de
Swiss Ephemeris, la misma efeméride que dibuja las cartas: las próximas fases,
del cruce del ángulo Luna − Sol por 0°, 90°, 180° y 270° (coinciden al minuto
con el U.S. Naval Observatory), y el cambio de signo, de `swe.mooncross_ut`."""

from __future__ import annotations

from datetime import datetime, timezone

import swisseph as swe
from kerykeion import AstrologicalSubjectFactory
from kerykeion.moon_phase_details.factory import MoonPhaseDetailsFactory
from kerykeion.moon_phase_details.utils import configure_ephemeris_path
from kerykeion.schemas.kr_models import MoonPhaseMoonSummaryModel
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


def _moon(utc: datetime) -> MoonPhaseMoonSummaryModel:
    subject = AstrologicalSubjectFactory.from_birth_data(
        "Sky", utc.year, utc.month, utc.day, utc.hour, utc.minute,
        lng=0.0, lat=0.0, tz_str="UTC", online=False,
    )
    return MoonPhaseDetailsFactory.from_subject(subject).moon


# Ángulo Luna − Sol de cada fase.
_ANGULOS = {"new_moon": 0.0, "first_quarter": 90.0, "full_moon": 180.0, "last_quarter": 270.0}
# Velocidad media de la elongación (°/día): sólo para el primer tanteo.
_VELOCIDAD_MEDIA = 360.0 / 29.530588


def _elongacion(jd: float) -> tuple[float, float]:
    """El ángulo Luna − Sol en `jd`, en [0, 360), y cuánto cambia por día."""
    luna = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH | swe.FLG_SPEED)[0]
    sol = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH | swe.FLG_SPEED)[0]
    return (float(luna[0]) - float(sol[0])) % 360.0, float(luna[3]) - float(sol[3])


def _proxima_fase(angulo: float, jd: float) -> float:
    """El primer instante estrictamente posterior a `jd` en que la elongación
    llega a `angulo`.

    Antes lo buscaba kerykeion, y hasta ~23 h después de una luna nueva
    devolvía como «próxima» el mismo instante consultado (medido el
    10-10-2026). Acá es Newton sobre la elongación, que siempre crece (11 a
    15 °/día): el tanteo con la velocidad media cae a menos de ±4 días del
    cruce bueno, y las fases iguales están a 29,5 días, así que converge al
    que corresponde."""
    actual, _ = _elongacion(jd)
    falta = (angulo - actual) % 360.0 or 360.0
    t = jd + falta / _VELOCIDAD_MEDIA
    for _ in range(30):
        e, velocidad = _elongacion(t)
        error = (angulo - e + 180.0) % 360.0 - 180.0
        t += error / velocidad
        if abs(error) < 1e-7:
            break
    else:
        raise RuntimeError(f"la fase de {angulo}° no convergió")
    return t


def moon_state(moment: datetime) -> MoonState:
    """La Luna en `moment`, que tiene que traer zona horaria."""
    if moment.tzinfo is None:
        raise ValueError("moon_state necesita un datetime con zona horaria")
    utc = moment.astimezone(timezone.utc)

    moon = _moon(utc)
    configure_ephemeris_path()
    jd = datetime_to_julian(utc)
    events = [
        PhaseEvent(
            phase=phase,
            moment=julian_to_datetime(_proxima_fase(_ANGULOS[phase], jd)).replace(tzinfo=timezone.utc),
        )
        for phase in _MAJOR_PHASES
    ]
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
