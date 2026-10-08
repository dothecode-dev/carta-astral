import pytest
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework.throttling import ScopedRateThrottle

from api import lectura_anonima as la

pytestmark = pytest.mark.django_db
URL = "/api/lectura-anonima/"
CARTA = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
}


@pytest.fixture(autouse=True)
def _base(settings, monkeypatch):
    cache.clear()
    settings.INTERPRETATION_ANON_DAILY_CAP = 40
    monkeypatch.setattr(la, "_build_client", lambda: object())
    monkeypatch.setattr(la.informe_service, "escribir_breve", lambda *a: "breve")
    monkeypatch.setattr(la, "_arrancar_en_hilo", la.generar)
    monkeypatch.setattr(
        ScopedRateThrottle, "THROTTLE_RATES",
        {**ScopedRateThrottle.THROTTLE_RATES, "lectura_anonima": "3/day"},
    )


def _post(c, token=None, **extra):
    headers = {"HTTP_X_LECTURA_TOKEN": token} if token else {}
    return c.post(URL, {**CARTA, "lang": "es", **extra}, format="json", **headers)


def test_post_202_y_get_lista():
    c = APIClient()
    r = _post(c)
    assert r.status_code == 202 and r.json()["estado"] == "generando"
    token = r.json()["token"]
    g = c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    assert g.status_code == 200 and g.json()["texto"] == "breve"
    assert c.get(URL, HTTP_X_LECTURA_TOKEN=token).status_code == 404


def test_datos_invalidos_400():
    r = APIClient().post(URL, {"lang": "es"}, format="json")
    assert r.status_code == 400 and r.json()["motivo"] == "datos"


def test_idioma_invalido_400():
    assert _post(APIClient(), lang="fr").status_code == 400


def test_trato_invalido_400():
    assert _post(APIClient(), trato="otro").status_code == 400


def test_usado_409():
    c = APIClient()
    token = _post(c).json()["token"]
    c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    r = _post(c, token)
    assert r.status_code == 409 and r.json()["motivo"] == "usado"


def test_cuarto_pedido_de_la_misma_ip_429():
    c = APIClient()
    for _ in range(3):
        assert _post(c).status_code == 202
    r = _post(c)
    assert r.status_code == 429 and r.json()["motivo"] == "ip"


def test_ocupado_no_cuenta_para_la_ip(settings):
    settings.LECTURA_ANONIMA_CONCURRENCIA = 1
    cache.add("lectura_anonima:slot:0", "otro", timeout=90)
    c = APIClient()
    for _ in range(4):
        r = _post(c)
        assert r.status_code == 503 and r.json()["motivo"] == "ocupado"
    cache.delete("lectura_anonima:slot:0")
    assert _post(c).status_code == 202


def test_mantenimiento_503(monkeypatch):
    monkeypatch.setattr(la.mantenimiento, "activo", lambda: True)
    r = _post(APIClient())
    assert r.status_code == 503 and r.json()["motivo"] == "mantenimiento"


def test_cupo_503(settings):
    settings.INTERPRETATION_ANON_DAILY_CAP = 0
    r = _post(APIClient())
    assert r.status_code == 503 and r.json()["motivo"] == "cupo"


def test_get_sin_token_404():
    assert APIClient().get(URL).status_code == 404


def test_el_get_no_cuenta_para_la_ip():
    c = APIClient()
    token = _post(c).json()["token"]
    for _ in range(10):
        c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    assert _post(c).status_code == 202
