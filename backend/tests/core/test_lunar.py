"""La Luna de un instante: fase, próximas fases y próximo cambio de signo.

Las fechas de referencia NO salen del propio motor: son las del U.S. Naval
Observatory (aa.usno.navy.mil/api/moon/phases/date), que publica las fases al
minuto. Compararse contra la propia salida no probaría nada.
"""

import datetime

import pytest

from core.ephemeris import sky_now
from core.lunar import moon_state

UTC = datetime.timezone.utc


def _utc(*args: int) -> datetime.datetime:
    return datetime.datetime(*args, tzinfo=UTC)


def _moon_sign(moment: datetime.datetime) -> str:
    return next(b.sign for b in sky_now(moment) if b.name == "Moon")


# USNO, octubre de 2026 y enero de 2024.
USNO = [
    (_utc(2026, 10, 1), "new_moon", _utc(2026, 10, 10, 15, 50)),
    (_utc(2026, 10, 1), "first_quarter", _utc(2026, 10, 18, 16, 12)),
    (_utc(2026, 10, 1), "full_moon", _utc(2026, 10, 26, 4, 12)),
    (_utc(2024, 1, 1), "last_quarter", _utc(2024, 1, 4, 3, 30)),
    (_utc(2024, 1, 1), "new_moon", _utc(2024, 1, 11, 11, 57)),
    (_utc(2024, 1, 1), "full_moon", _utc(2024, 1, 25, 17, 54)),
]


@pytest.mark.parametrize(("moment", "phase", "expected"), USNO)
def test_la_proxima_fase_coincide_con_el_observatorio_naval(moment, phase, expected):
    state = moon_state(moment)

    found = next(p.moment for p in state.next_phases if p.phase == phase)
    # USNO redondea al minuto: un minuto de margen es su propia precisión.
    assert abs((found - expected).total_seconds()) <= 60


def test_las_proximas_fases_son_las_cuatro_en_orden_y_en_el_futuro():
    moment = _utc(2026, 10, 1)
    state = moon_state(moment)

    phases = [p.phase for p in state.next_phases]
    assert sorted(phases) == sorted(["new_moon", "first_quarter", "full_moon", "last_quarter"])
    moments = [p.moment for p in state.next_phases]
    assert moments == sorted(moments)
    assert all(m > moment for m in moments)


def test_la_fase_de_ahora_dice_si_crece_y_cuanto_se_ve():
    # El 01-10-2026 la Luna viene de llena (26-09) hacia el cuarto menguante
    # del 03-10: menguante y bastante iluminada.
    state = moon_state(_utc(2026, 10, 1))

    assert state.phase == "waning_gibbous"
    assert state.waxing is False
    assert 60 <= state.illumination <= 90


def test_en_luna_llena_se_ve_entera_y_en_luna_nueva_no_se_ve():
    assert moon_state(_utc(2026, 10, 26, 4, 12)).illumination >= 99
    assert moon_state(_utc(2026, 10, 10, 15, 50)).illumination <= 1


def test_el_cambio_de_signo_coincide_con_el_motor_de_las_cartas():
    # La página y la rueda tienen que decir lo mismo: un minuto antes del
    # cambio la Luna sigue en el signo de ahora, un minuto después ya está en
    # el siguiente, medido con `sky_now`, que es lo que dibuja la portada.
    moment = _utc(2026, 10, 1)
    state = moon_state(moment)
    change = state.next_sign_change

    assert state.sign == "Gem" == _moon_sign(moment)
    assert change.sign == "Can"
    before = (change.moment - datetime.timedelta(minutes=2)).replace(second=0, microsecond=0)
    after = (change.moment + datetime.timedelta(minutes=2)).replace(second=0, microsecond=0)
    assert _moon_sign(before) == "Gem"
    assert _moon_sign(after) == "Can"


def test_el_cambio_de_signo_de_piscis_vuelve_a_aries():
    # El cruce de 360° a 0° es el único borde donde una cuenta mal hecha
    # buscaría el grado 360, que no existe.
    moment = _utc(2026, 10, 1)
    for _ in range(30):
        if moon_state(moment).sign == "Pis":
            break
        moment += datetime.timedelta(days=1)
    state = moon_state(moment)

    assert state.sign == "Pis"
    assert state.next_sign_change.sign == "Ari"
    assert state.next_sign_change.moment > moment


def test_acepta_sólo_instantes_con_zona_horaria():
    # Un datetime sin zona es ambiguo, y la Luna se mueve medio grado por hora.
    with pytest.raises(ValueError):
        moon_state(datetime.datetime(2026, 10, 1))


# Las fases del USNO de arriba, consultadas un poco antes y un poco después.
# Cuando las buscaba kerykeion, hasta ~23 h después de una luna nueva devolvía
# como «próxima» el instante consultado (medido el 10-10-2026: a las 16:00
# decía que la próxima era a las 16:00, y era el 09-11). Los cuartos y la
# llena no fallaban, pero se prueban igual: el cálculo es el mismo para las
# cuatro. La referencia es la misma fase consultada una semana después.
RECIEN_PASADA = [
    ("new_moon", _utc(2026, 10, 10, 15, 50)),
    ("first_quarter", _utc(2026, 10, 18, 16, 12)),
    ("full_moon", _utc(2026, 10, 26, 4, 12)),
    ("last_quarter", _utc(2024, 1, 4, 3, 30)),
]


@pytest.mark.parametrize(("phase", "fase_pasada"), RECIEN_PASADA)
@pytest.mark.parametrize("despues", [datetime.timedelta(minutes=2), datetime.timedelta(hours=12)])
def test_justo_despues_de_una_fase_la_proxima_es_la_siguiente(phase, fase_pasada, despues):
    moment = fase_pasada + despues

    found = next(p.moment for p in moon_state(moment).next_phases if p.phase == phase)
    referencia = next(
        p.moment for p in moon_state(fase_pasada + datetime.timedelta(days=7)).next_phases
        if p.phase == phase
    )

    assert found > moment
    assert abs((found - referencia).total_seconds()) <= 60


@pytest.mark.parametrize(("phase", "fase"), RECIEN_PASADA)
@pytest.mark.parametrize("antes", [datetime.timedelta(minutes=2), datetime.timedelta(hours=12)])
def test_justo_antes_de_una_fase_la_proxima_es_esa(phase, fase, antes):
    found = next(p.moment for p in moon_state(fase - antes).next_phases if p.phase == phase)

    # USNO redondea al minuto.
    assert abs((found - fase).total_seconds()) <= 60
