"""RF1 y RF4 de la spec de Vínculo: la sinastría coincide con astro.com.

Se comparan POSICIONES (±0,01°) y el ÁNGULO de cada aspecto que devuelve la
función (±0,05°), no qué aspectos aparecen: eso depende de la tabla de orbes,
y cada sitio usa la suya.

Fuentes, consultadas el 05-10-2026. Las posiciones son las de la tabla de la
rueda natal (Placidus, con segundos de arco) de cada ficha del Astro-Databank:

- Obama:  https://www.astro.com/astro-databank/Obama,_Barack
  4-8-1961 19:24, Honolulu (21n18, 157w52), AHST h10w. Rodden AA, «BC/BR in hand».
- Messi:  https://www.astro.com/astro-databank/Messi,_Lionel
  24-6-1987 20:30, Rosario (32s57, 60w40), -03 h3w. Rodden AA, «BC/BR in hand».

Los dos son de la clasificación AA y de después de 1950 (sin LMT ni
`precision_degraded`), en hemisferios y husos distintos. Ninguno tiene horario
de verano: la hora local es inequívoca. Eso lo cubren `test_golden.py` y
`test_fechas_extremas.py`; acá se prueba que la sinastría lee lo mismo.

Los números se dejan como los muestra astro.com —(signo, grado, minuto,
segundo)— y se convierten acá, para poder auditarlos contra la fuente a ojo.
"""

import datetime

import pytest

from core.ephemeris import build_chart
from core.models import BirthInput, ChartData
from core.sinastria import aspectos_cruzados

SIGNOS = ["Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis"]


def _sep(a: float, b: float) -> float:
    """Distancia angular entre dos longitudes, escrita acá a propósito: usar la
    `separacion` del código bajo prueba haría que el test se validara a sí mismo."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


def _lon(signo: str, grado: int, minuto: int, segundo: int) -> float:
    return SIGNOS.index(signo) * 30 + grado + minuto / 60 + segundo / 3600


# Obama, 4-8-1961 19:24, Honolulu.
NAC_A = BirthInput(
    name=None, date=datetime.date(1961, 8, 4), time=datetime.time(19, 24), time_known=True,
    lat=21 + 18 / 60, lng=-(157 + 52 / 60),
)
ASTRO_A = {
    "Sun": _lon("Leo", 12, 32, 53),
    "Moon": _lon("Gem", 3, 21, 27),
    "Mercury": _lon("Leo", 2, 19, 54),
    "Venus": _lon("Can", 1, 47, 22),
    "Mars": _lon("Vir", 22, 34, 36),
    "Jupiter": _lon("Aqu", 0, 51, 31),
    "Saturn": _lon("Cap", 25, 19, 51),
    "Uranus": _lon("Leo", 25, 16, 15),
    "Neptune": _lon("Sco", 8, 36, 21),
    "Pluto": _lon("Vir", 6, 58, 40),
    "Ascendant": _lon("Aqu", 18, 2, 41),
    "Medium_Coeli": _lon("Sco", 28, 53, 7),
}

# Messi, 24-6-1987 20:30, Rosario.
NAC_B = BirthInput(
    name=None, date=datetime.date(1987, 6, 24), time=datetime.time(20, 30), time_known=True,
    lat=-(32 + 57 / 60), lng=-(60 + 40 / 60),
)
ASTRO_B = {
    "Sun": _lon("Can", 2, 54, 55),
    "Moon": _lon("Gem", 19, 2, 37),
    "Mercury": _lon("Can", 16, 16, 21),
    "Venus": _lon("Gem", 16, 45, 20),
    "Mars": _lon("Can", 22, 30, 4),
    "Jupiter": _lon("Ari", 25, 2, 17),
    "Saturn": _lon("Sag", 16, 43, 38),
    "Uranus": _lon("Sag", 24, 23, 9),
    "Neptune": _lon("Cap", 6, 43, 42),
    "Pluto": _lon("Sco", 7, 17, 51),
    "Ascendant": _lon("Aqu", 4, 58, 43),
    "Medium_Coeli": _lon("Lib", 26, 19, 29),
}

TOL_POSICION = 0.01
TOL_ANGULO = 0.05


def _posiciones(carta: ChartData) -> dict[str, float]:
    pos = {p.name: p.abs_pos for p in carta.placements}
    pos.update({g.name: g.abs_pos for g in carta.angles or []})
    return pos


def test_posiciones_coinciden_con_astro_com():
    for nac, astro in ((NAC_A, ASTRO_A), (NAC_B, ASTRO_B)):
        pos = _posiciones(build_chart(nac))
        for punto, esperado in astro.items():
            diff = _sep(pos[punto], esperado)
            assert diff <= TOL_POSICION, f"{punto}: {pos[punto]:.4f} vs {esperado:.4f} ({diff:.4f}°)"


def test_angulo_de_cada_aspecto_coincide_con_astro_com():
    a, b = build_chart(NAC_A), build_chart(NAC_B)
    asps = aspectos_cruzados(a, b)
    assert asps, "el par elegido tiene que tener aspectos cruzados"
    for asp in asps:
        esperado = _sep(ASTRO_A[asp.p_a], ASTRO_B[asp.p_b])
        assert abs(asp.angulo - esperado) <= TOL_ANGULO, (asp.p_a, asp.p_b)


def test_la_sinastria_usa_las_mismas_posiciones_que_la_carta():
    """RF4: no hay un segundo cálculo; la carta y el vínculo leen lo mismo."""
    a, b = build_chart(NAC_A), build_chart(NAC_B)
    pos_a, pos_b = _posiciones(a), _posiciones(b)
    for asp in aspectos_cruzados(a, b):
        assert asp.angulo == pytest.approx(_sep(pos_a[asp.p_a], pos_b[asp.p_b]), abs=1e-9)
