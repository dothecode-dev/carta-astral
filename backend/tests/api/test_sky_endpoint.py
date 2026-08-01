"""El endpoint público del cielo actual, que consume la portada del sitio.

Es la única ruta de datos sin autenticación del proyecto, así que lo que más
importa verificar es lo que NO expone y que no se pueda usar para hacer gastar
recursos.
"""

from unittest.mock import patch

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _limpiar_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_responde_sin_autenticacion():
    # La portada es pública y estática: no hay ninguna cuenta detrás.
    resp = APIClient().get("/api/sky/")

    assert resp.status_code == 200


@pytest.mark.django_db
def test_devuelve_los_diez_cuerpos_con_su_longitud():
    body = APIClient().get("/api/sky/").json()

    assert [b["name"] for b in body["bodies"]] == [
        "Sun", "Moon", "Mercury", "Venus", "Mars",
        "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
    ]
    for planet in body["bodies"]:
        assert 0.0 <= planet["longitude"] < 360.0
        assert set(planet) == {"name", "sign", "longitude", "retrograde"}


@pytest.mark.django_db
def test_no_expone_casas_ni_datos_de_nadie():
    body = APIClient().get("/api/sky/").json()

    assert set(body) == {"moment", "bodies"}
    plano = str(body)
    for prohibido in ("house", "ascendant", "birth", "account", "email"):
        assert prohibido not in plano.lower()


@pytest.mark.django_db
def test_el_instante_viene_truncado_al_minuto():
    # La rueda se redibuja cada 30 s; devolver segundos sólo rompería el cache.
    moment = APIClient().get("/api/sky/").json()["moment"]

    assert moment.endswith(":00+00:00")


@pytest.mark.django_db
def test_no_recalcula_en_cada_pedido():
    # Sin cache, cualquiera puede hacer que el servidor calcule efemérides en
    # loop. Con cache, la segunda llamada del mismo minuto sale de memoria.
    client = APIClient()
    with patch("api.sky.sky_now", wraps=None) as spy:
        spy.return_value = []
        client.get("/api/sky/")
        client.get("/api/sky/")

    assert spy.call_count == 1


@pytest.mark.django_db
def test_solo_acepta_get():
    resp = APIClient().post("/api/sky/", {})

    assert resp.status_code == 405
