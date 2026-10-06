"""La vista previa de Vínculo: dos personas, sin cuenta, sin guardar, sin LLM.

Es la fase 1 de Vínculo (spec, sección 10): se publica para medir la demanda
antes de construir la compra. Como `test_chart_preview.py`, lo que se prueba
es tanto lo que hace como lo que NO hace.
"""

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db

URL = "/api/vinculo/preview/"
A = {"date": "1976-05-31", "time": "19:30", "time_known": True,
     "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR"}
B = {"date": "1980-11-02", "time": "08:15", "time_known": True,
     "lat": -31.42, "lng": -64.18, "place_label": "Córdoba, AR"}
PERSONALES = ("Sun", "Moon", "Mercury", "Venus", "Mars")


@pytest.fixture(autouse=True)
def _encendido(settings):
    settings.VINCULO_PREVIEW_ENABLED = True
    cache.clear()


def _post(payload):
    return APIClient().post(URL, payload, format="json")


def test_devuelve_las_dos_cartas_y_hasta_cuatro_aspectos():
    r = _post({"lang": "es", "a": A, "b": B})
    assert r.status_code == 200, r.data
    assert r.data["a"]["data"]["placements"] and r.data["b"]["data"]["placements"]
    assert 0 < len(r.data["aspectos"]) <= 4
    for asp in r.data["aspectos"]:
        assert asp["p_a"] in PERSONALES and asp["p_b"] in PERSONALES
        assert asp["frase"]


def test_aspectos_ordenados_por_orbe():
    r = _post({"lang": "es", "a": A, "b": B})
    orbes = [x["orbe"] for x in r.data["aspectos"]]
    assert orbes == sorted(orbes)


def test_la_frase_sale_en_el_idioma_pedido():
    es = _post({"lang": "es", "a": A, "b": B}).data["aspectos"][0]["frase"]
    en = _post({"lang": "en", "a": A, "b": B}).data["aspectos"][0]["frase"]
    assert es != en


def test_no_devuelve_identificadores():
    r = _post({"lang": "es", "a": A, "b": B})
    for lado in ("a", "b"):
        assert "uuid" not in r.data[lado] and "id" not in r.data[lado]


def test_no_guarda_nada():
    _post({"lang": "es", "a": A, "b": B})
    assert Chart.objects.count() == 0
    assert BirthData.objects.count() == 0


def test_no_llama_al_modelo(monkeypatch):
    def explota(*a, **k):
        raise AssertionError("la vista previa no puede llamar al LLM")

    monkeypatch.setattr("api.interpretation_service._build_client", explota)
    assert _post({"lang": "es", "a": A, "b": B}).status_code == 200


def test_misma_persona_es_400():
    r = _post({"lang": "es", "a": A, "b": dict(A)})
    assert r.status_code == 400
    assert r.data["error"] == "misma_persona"


def test_misma_persona_aunque_cambie_la_etiqueta_del_lugar():
    """La etiqueta es sólo display: mismas coordenadas, misma persona."""
    r = _post({"lang": "es", "a": A, "b": {**A, "place_label": "Otro nombre"}})
    assert r.status_code == 400
    assert r.data["error"] == "misma_persona"


@pytest.mark.parametrize("b", [
    {"date": "1980-11"},
    {**B, "date": "1980-11"},
    {**B, "lat": "norte"},
    None,
    "texto",
])
def test_datos_invalidos_es_400(b):
    r = _post({"lang": "es", "a": A, "b": b})
    assert r.status_code == 400
    assert r.data["error"] == "datos_invalidos"


def test_sin_personas_es_400():
    r = _post({"lang": "es"})
    assert r.status_code == 400
    assert r.data["error"] == "datos_invalidos"


def test_idioma_desconocido_cae_en_espanol():
    r = _post({"lang": "xx", "a": A, "b": B})
    es = _post({"lang": "es", "a": A, "b": B})
    assert r.status_code == 200
    assert r.data["aspectos"] == es.data["aspectos"]


def test_persona_sin_hora_no_aporta_angulos():
    sin_hora = {**B, "time": None, "time_known": False}
    r = _post({"lang": "es", "a": A, "b": sin_hora})
    assert r.status_code == 200
    assert r.data["b"]["data"]["houses"] is None
    assert all(x["p_b"] in PERSONALES for x in r.data["aspectos"])


def test_sin_aspectos_personales_devuelve_lista_vacia(monkeypatch):
    monkeypatch.setattr("api.vinculo.aspectos_cruzados", lambda a, b: [])
    r = _post({"lang": "es", "a": A, "b": B})
    assert r.status_code == 200
    assert r.data["aspectos"] == []


def test_flag_apagado_la_vista_previa_es_404(settings):
    settings.VINCULO_PREVIEW_ENABLED = False
    assert _post({"lang": "es", "a": A, "b": B}).status_code == 404


def test_estado_con_flag_encendido():
    r = APIClient().get("/api/vinculo/")
    assert r.status_code == 200
    assert r.data == {"preview": True}


def test_estado_con_flag_apagado_responde_200_y_dice_false(settings):
    """El estado se INFORMA, no se esconde con un 404.

    La web guarda esta respuesta en el caché de datos de Next, que sólo guarda
    las 200: con un 404 de «apagado», el valor viejo («encendido») quedaba
    vigente para siempre y apagar el flag no apagaba la landing (comprobado el
    05-10-2026 con un backend de mentira). Un 200 con el valor se cachea igual
    en los dos sentidos."""
    settings.VINCULO_PREVIEW_ENABLED = False
    r = APIClient().get("/api/vinculo/")
    assert r.status_code == 200
    assert r.data == {"preview": False}


def test_hay_techo_por_ip(monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", {"preview": "1/day"},
    )
    assert _post({"lang": "es", "a": A, "b": B}).status_code == 200
    assert _post({"lang": "es", "a": A, "b": B}).status_code == 429
