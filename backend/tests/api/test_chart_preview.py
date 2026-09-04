"""`POST /api/charts/preview/`: la carta del visitante que todavía no tiene cuenta.

Existe para que quien llega de una búsqueda o de Instagram vea SU rueda antes
de que se le pida nada. Es la única vista del cálculo abierta al público, así
que lo que se prueba acá es tanto lo que hace como lo que NO hace: no guarda
nada, no devuelve identificadores y no es una puerta para gastar CPU gratis.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from api.auth import create_session
from api.models import Account, BirthData, Chart

pytestmark = pytest.mark.django_db

URL = "/api/charts/preview/"
PAYLOAD = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
}


@pytest.fixture(autouse=True)
def _sin_contadores_viejos():
    cache.clear()


def test_sin_sesion_devuelve_la_carta():
    r = APIClient().post(URL, PAYLOAD, format="json")
    assert r.status_code == 200, r.data
    assert r.data["data"]["placements"]
    assert r.data["data"]["houses"]


def test_no_guarda_nada():
    """Lo que se calcula para un anónimo no deja rastro: ni carta ni fecha de
    nacimiento. Es dato sensible de alguien que no aceptó nada todavía."""
    APIClient().post(URL, PAYLOAD, format="json")
    assert Chart.objects.count() == 0
    assert BirthData.objects.count() == 0


def test_no_devuelve_identificadores():
    """Sin uuid no hay nada que pedirle al backend después: el preview no es
    una carta a medio crear, es un cálculo y se acabó."""
    r = APIClient().post(URL, PAYLOAD, format="json")
    assert "uuid" not in r.data
    assert "id" not in r.data


def test_hora_desconocida_no_trae_casas():
    r = APIClient().post(
        URL, {**PAYLOAD, "time": None, "time_known": False}, format="json",
    )
    assert r.status_code == 200
    assert r.data["data"]["houses"] is None


def test_payload_invalido_es_400():
    r = APIClient().post(URL, {"date": "no-es-una-fecha"}, format="json")
    assert r.status_code == 400


def test_con_sesion_tambien_anda_y_sigue_sin_guardar():
    """El mismo formulario lo usa quien ya entró: no se bifurca el camino."""
    acc = Account.objects.create()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    assert c.post(URL, PAYLOAD, format="json").status_code == 200
    assert Chart.objects.count() == 0


def test_hay_techo_por_ip(monkeypatch):
    """Sin cuenta no hay a quién cobrarle el abuso: el techo es la IP."""
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"preview": "1/day"},
    )
    cache.clear()
    c = APIClient()
    assert c.post(URL, PAYLOAD, format="json").status_code == 200
    assert c.post(URL, PAYLOAD, format="json").status_code == 429
