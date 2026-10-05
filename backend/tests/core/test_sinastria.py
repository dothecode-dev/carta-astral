"""Geometría de la sinastría sobre cartas sintéticas.

Las cartas se arman a mano para que cada ángulo sea obvio: la validación
contra una fuente externa vive en `test_sinastria_externa.py`.
"""

import dataclasses

from core.models import Angle, ChartData, DegradationFlags, House, Placement
from core.sinastria import ORBES, aspectos_cruzados


def _carta(posiciones: dict[str, float], hora: bool = True) -> ChartData:
    placements = [
        Placement(name=n, sign="Ari", position=p % 30, abs_pos=p, house=None, retrograde=False)
        for n, p in posiciones.items()
    ]
    angles = (
        [Angle(name="Ascendant", sign="Ari", abs_pos=0.0),
         Angle(name="Medium_Coeli", sign="Cap", abs_pos=270.0)]
        if hora else None
    )
    houses = (
        [House(name=f"H{i}", sign="Ari", abs_pos=i * 30.0) for i in range(12)]
        if hora else None
    )
    return ChartData(
        placements=placements, houses=houses, angles=angles, aspects=[],
        zodiac="Tropical", house_system="Placidus", time_known=hora,
        flags=DegradationFlags(), julian_day=0.0, utc_iso="2000-01-01T00:00:00+00:00",
    )


def _par(asps, p_a, p_b):
    return [x for x in asps if x.p_a == p_a and x.p_b == p_b]


def test_conjuncion_exacta():
    a = _carta({"Sun": 10.0})
    b = _carta({"Moon": 10.0})
    [asp] = _par(aspectos_cruzados(a, b), "Sun", "Moon")
    assert asp.aspecto == "conjunction"
    assert asp.orbe == 0.0


def test_cruza_el_cero_de_aries():
    """358° y 2° están a 4°, no a 356°."""
    a = _carta({"Sun": 358.0})
    b = _carta({"Moon": 2.0})
    [asp] = _par(aspectos_cruzados(a, b), "Sun", "Moon")
    assert asp.aspecto == "conjunction"
    assert abs(asp.orbe - 4.0) < 1e-9


def test_cuadratura_con_orbe():
    a = _carta({"Mars": 100.0})
    b = _carta({"Venus": 13.0})
    [asp] = _par(aspectos_cruzados(a, b), "Mars", "Venus")
    assert asp.aspecto == "square"
    assert abs(asp.orbe - 3.0) < 1e-9
    assert abs(asp.angulo - 87.0) < 1e-9


def test_fuera_de_orbe_no_hay_aspecto():
    a = _carta({"Sun": 0.0})
    b = _carta({"Moon": 60.0 + ORBES["sextile"] + 0.1})
    assert _par(aspectos_cruzados(a, b), "Sun", "Moon") == []


def test_es_direccional_a_contra_b():
    """El Sol de A con la Luna de B no es la Luna de A con el Sol de B."""
    a = _carta({"Sun": 0.0, "Moon": 200.0})
    b = _carta({"Sun": 200.0, "Moon": 0.0})
    asps = aspectos_cruzados(a, b)
    assert _par(asps, "Sun", "Moon")[0].aspecto == "conjunction"
    assert _par(asps, "Moon", "Sun")[0].aspecto == "conjunction"
    # Sol de A (0°) y Sol de B (200°) están a 160°: ningún aspecto mayor.
    assert _par(asps, "Sun", "Sun") == []


def test_ordenado_por_orbe():
    a = _carta({"Sun": 0.0, "Moon": 0.0})
    b = _carta({"Sun": 3.0, "Moon": 1.0})
    orbes = [x.orbe for x in aspectos_cruzados(a, b)]
    assert orbes == sorted(orbes)


def test_con_hora_entran_ascendente_y_mc():
    a = _carta({"Sun": 0.0})
    b = _carta({"Moon": 270.0})
    nombres = {(x.p_a, x.p_b) for x in aspectos_cruzados(a, b)}
    assert ("Ascendant", "Ascendant") in nombres
    assert ("Sun", "Medium_Coeli") in nombres


def test_sin_hora_no_entran_sus_angulos():
    """RF3: sin hora de B no hay Ascendente ni MC de B en ningún aspecto."""
    a = _carta({"Sun": 0.0})
    b = _carta({"Moon": 0.0}, hora=False)
    puntos_b = {x.p_b for x in aspectos_cruzados(a, b)}
    assert "Ascendant" not in puntos_b
    assert "Medium_Coeli" not in puntos_b


def test_time_known_falso_manda_aunque_haya_angulos():
    """La decisión es por `time_known`, no por si `angles` vino vacío: una carta
    marcada sin hora no aporta Ascendente aunque alguien le haya dejado ángulos."""
    a = _carta({"Sun": 0.0})
    b = dataclasses.replace(_carta({"Moon": 0.0}), time_known=False)
    assert b.angles  # el caso que importa: ángulos presentes, hora desconocida
    puntos_b = {x.p_b for x in aspectos_cruzados(a, b)}
    assert "Ascendant" not in puntos_b


def test_cuerpos_fuera_de_puntos_no_entran():
    """Quirón, nodos y Lilith quedan fuera: la tabla de puntos es cerrada."""
    # Las dos sin hora: si no, el Ascendente de A (0°) haría conjunción con el Sol de B.
    a = _carta({"Chiron": 0.0}, hora=False)
    b = _carta({"Sun": 0.0}, hora=False)
    assert aspectos_cruzados(a, b) == []
