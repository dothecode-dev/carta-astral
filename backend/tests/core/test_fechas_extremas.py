"""Fechas fuera del alcance de algunas efemérides.

Swiss Ephemeris no cubre todos los cuerpos en todo el rango de fechas: la de
Quirón arranca alrededor del año 675. Kerykeion, cuando no puede calcular uno,
loguea el error y devuelve None en vez de fallar — y leerle el nombre a ese None
tiraba un 500 en el endpoint de cartas.

Nadie nace en el año 1, pero un dedo en el formulario alcanza para llegar acá, y
la respuesta a una fecha rara no puede ser un error del servidor.
"""

import datetime

import pytest

from core.ephemeris import build_chart
from core.models import BirthInput


def _birth(year: int) -> BirthInput:
    return BirthInput(
        name="Prueba", date=datetime.date(year, 9, 16), time=datetime.time(5, 45),
        time_known=True, lat=-34.61, lng=-58.38,
        house_system="Placidus", zodiac="Tropical",
    )


def test_una_fecha_anterior_a_la_efemeride_de_quiron_no_explota():
    chart = build_chart(_birth(1))

    assert chart.placements, "debería devolver los cuerpos que sí se pudieron calcular"


def test_devuelve_los_cuerpos_que_si_se_pudieron_calcular():
    chart = build_chart(_birth(1))
    nombres = {p.name for p in chart.placements}

    # El Sol y la Luna se calculan en todo el rango; Quirón no.
    assert {"Sun", "Moon"} <= nombres
    assert "Chiron" not in nombres


def test_avisa_que_la_carta_quedo_incompleta():
    chart = build_chart(_birth(1))

    assert chart.flags.bodies_missing is True
    assert chart.flags.precision_degraded is True


def test_una_fecha_normal_trae_todo_y_sin_marca():
    chart = build_chart(_birth(1994))
    nombres = {p.name for p in chart.placements}

    assert "Chiron" in nombres
    assert chart.flags.bodies_missing is False


@pytest.mark.parametrize("year", [1, 500, 674])
def test_varias_fechas_del_rango_problematico(year):
    chart = build_chart(_birth(year))

    assert chart.placements
    assert chart.flags.bodies_missing is True
