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


def test_la_vista_previa_trae_la_firma():
    """Sol, Luna y Ascendente en palabras: lo único de la carta que entiende
    quien no sabe leer glifos, y va también para quien no tiene cuenta."""
    r = APIClient().post(URL, PAYLOAD, format="json")
    assert [linea["cuerpo"] for linea in r.data["firma"]] == ["Sun", "Moon", "Ascendant"]
    assert r.data["firma"][0]["frases"]["es"]


def test_campo_faltante_dice_cual_falta_sin_repr_de_la_excepcion():
    """Un `KeyError` pelado se serializaba como `"'date'"`: el repr de Python."""
    sin_fecha = {k: v for k, v in PAYLOAD.items() if k != "date"}
    r = APIClient().post(URL, sin_fecha, format="json")
    assert r.status_code == 400
    assert r.data["error"] == "falta el campo date"


@pytest.mark.parametrize("campo,valor", [("date", 123), ("lat", [1]), ("lng", {"a": 1}), ("time", 5)])
def test_valores_de_tipo_equivocado_dan_400_no_500(campo, valor):
    r = APIClient().post(URL, {**PAYLOAD, campo: valor}, format="json")
    assert r.status_code == 400, r.data


# --- Validación del payload entero (spec §11): todo dato inválido es 400, nunca 500.


def _crudo(**reemplazos):
    """El cuerpo JSON escrito a mano: `1e400` no se puede producir con
    `json.dumps` (saldría `Infinity`, que el parser ya rechaza)."""
    import json

    campos = {k: json.dumps(v) for k, v in PAYLOAD.items()}
    campos.update(reemplazos)
    return "{" + ",".join(f'"{k}": {v}' for k, v in campos.items()) + "}"


@pytest.mark.parametrize("reemplazos", [
    {"lat": "1e400"}, {"lng": "-1e400"}, {"lat": "1" + "0" * 400}, {"lng": "-" + "9" * 400},
])
def test_numeros_fuera_de_rango_flotante_dan_400(reemplazos):
    r = APIClient().post(URL, _crudo(**reemplazos), content_type="application/json")
    assert r.status_code == 400, r.data


@pytest.mark.parametrize("campo,valor", [
    ("lat", 90.5), ("lat", -91), ("lng", 180.01), ("lng", -181),
    ("lat", True), ("lng", False), ("lat", "-34.5"), ("lat", None),
    ("house_system", ["x"]), ("house_system", "Inventado"), ("house_system", None),
    ("zodiac", "Chino"), ("zodiac", {"a": 1}),
    ("time_known", "sí"), ("time_known", 1),
    ("time", ["19:30"]), ("time", "no-es-hora"), ("date", None), ("date", ["1976-05-31"]),
    ("name", ["Ceci"]), ("name", "x" * 201), ("place_label", 5), ("place_label", "x" * 201),
])
def test_cada_campo_invalido_da_400(campo, valor):
    r = APIClient().post(URL, {**PAYLOAD, campo: valor}, format="json")
    assert r.status_code == 400, r.data


@pytest.mark.parametrize("extra", [
    {"house_system": "Whole Sign"}, {"house_system": "Koch"}, {"house_system": "Porphyry"},
    {"house_system": "Equal"}, {"zodiac": "Sidereal"}, {"name": None}, {"time": None, "time_known": False},
    {"lat": -34, "lng": -58},  # enteros: también son números
])
def test_los_valores_soportados_siguen_andando(extra):
    r = APIClient().post(URL, {**PAYLOAD, **extra}, format="json")
    assert r.status_code == 200, r.data


def test_sin_house_system_ni_zodiac_usa_los_de_siempre():
    r = APIClient().post(URL, PAYLOAD, format="json")
    assert r.status_code == 200
    assert r.data["house_system"] == "Placidus" and r.data["zodiac"] == "Tropical"
