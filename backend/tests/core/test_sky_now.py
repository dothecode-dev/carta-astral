"""El cielo del momento: posiciones sin datos de nacimiento.

Los tests no comparan contra la salida del propio motor (eso no probaría nada):
verifican hechos astronómicos que se cumplen con cualquier efeméride correcta.
"""

import datetime

from core.ephemeris import sky_now

UTC = datetime.timezone.utc


def _lon(bodies, name: str) -> float:
    return next(b.abs_pos for b in bodies if b.name == name)


def test_devuelve_los_cuerpos_del_sistema_solar():
    bodies = sky_now(datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC))

    names = [b.name for b in bodies]
    assert names == [
        "Sun", "Moon", "Mercury", "Venus", "Mars",
        "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    ]


def test_las_longitudes_caen_dentro_del_zodiaco():
    bodies = sky_now(datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC))

    for body in bodies:
        assert 0.0 <= body.abs_pos < 360.0, f"{body.name} fuera de rango"


def test_no_expone_casas_porque_no_hay_lugar_de_nacimiento():
    # Sin lugar no hay Ascendente ni casas: la rueda del sitio muestra signos,
    # no un mapa personal.
    bodies = sky_now(datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC))

    assert all(b.house is None for b in bodies)


def test_en_el_solsticio_de_junio_el_sol_entra_en_cancer():
    # El solsticio de junio es, por definición, el instante en que el Sol llega
    # a 90° de longitud eclíptica. En 2026 cae el 21 de junio.
    bodies = sky_now(datetime.datetime(2026, 6, 21, 8, 24, tzinfo=UTC))

    assert abs(_lon(bodies, "Sun") - 90.0) < 0.5


def test_en_el_equinoccio_de_marzo_el_sol_esta_en_cero_aries():
    bodies = sky_now(datetime.datetime(2026, 3, 20, 14, 46, tzinfo=UTC))

    sun = _lon(bodies, "Sun")
    assert min(sun, 360.0 - sun) < 0.5


def test_la_luna_se_mueve_mucho_mas_rapido_que_el_sol():
    # La Luna recorre unos 13° por día y el Sol algo menos de 1°. Si el cálculo
    # se equivocara de cuerpo o de unidades, esto no se cumpliría.
    antes = sky_now(datetime.datetime(2026, 8, 1, 0, 0, tzinfo=UTC))
    despues = sky_now(datetime.datetime(2026, 8, 2, 0, 0, tzinfo=UTC))

    def avance(name: str) -> float:
        delta = _lon(despues, name) - _lon(antes, name)
        return delta % 360.0

    assert 11.0 < avance("Moon") < 16.0
    assert 0.9 < avance("Sun") < 1.1


def test_el_lugar_no_cambia_las_longitudes():
    # Las posiciones son geocéntricas: se miden desde el centro de la Tierra, no
    # desde el observador. Por eso `sky_now` no recibe un lugar, y por eso la
    # rueda del sitio no necesita preguntar dónde está quien la mira.
    moment = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    buenos_aires = sky_now(moment, lat=-34.61, lng=-58.40)
    tokio = sky_now(moment, lat=35.68, lng=139.69)

    for a, b in zip(buenos_aires, tokio, strict=True):
        assert a.abs_pos == b.abs_pos, f"{a.name} cambió según el lugar"


def test_dos_llamadas_con_el_mismo_instante_dan_lo_mismo():
    moment = datetime.datetime(2026, 8, 1, 12, 0, tzinfo=UTC)

    assert sky_now(moment) == sky_now(moment)
