"""`POST /api/geocode/` sin cuenta: el formulario abierto tiene que resolver
el lugar de nacimiento.

Hasta el 04-09-2026 esta vista no declaraba permiso propio y heredaba
`HasAccount` del default de DRF, así que el visitante sin cuenta no podía ni
escribir dónde nació. Se abre con techo por IP: la base de GeoNames es
nuestra y una consulta es una consulta a la base.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

URL = "/api/geocode/"


@pytest.fixture(autouse=True)
def _sin_contadores_viejos():
    cache.clear()


def test_sin_sesion_puede_buscar_un_lugar():
    r = APIClient().post(URL, {"q": "Buenos Aires"}, format="json")
    assert r.status_code == 200, r.data
    assert "results" in r.data


def test_consulta_invalida_sigue_siendo_400():
    r = APIClient().post(URL, {"q": "a"}, format="json")
    assert r.status_code == 400


def test_hay_techo_por_ip(monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"geocode": "1/day"},
    )
    cache.clear()
    c = APIClient()
    assert c.post(URL, {"q": "Buenos Aires"}, format="json").status_code == 200
    assert c.post(URL, {"q": "Buenos Aires"}, format="json").status_code == 429
