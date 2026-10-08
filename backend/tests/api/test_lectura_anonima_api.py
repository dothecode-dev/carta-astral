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
PEDIDO = "11111111-1111-4111-8111-111111111111"
OTRO = "22222222-2222-4222-8222-222222222222"


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
    return c.post(URL, {**CARTA, "lang": "es", "pedido": PEDIDO, **extra}, format="json", **headers)


def test_post_202_y_get_lista():
    c = APIClient()
    r = _post(c)
    assert r.status_code == 202 and r.json()["estado"] == "generando"
    token = r.json()["token"]
    g = c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    assert g.status_code == 200 and g.json()["texto"] == "breve"
    assert g.json()["lang"] == "es" and g.json()["disclaimer"]
    assert g.json()["pedido"] == PEDIDO
    # Spec §11: el GET no borra; el DELETE (acuse) sí.
    assert c.get(URL, HTTP_X_LECTURA_TOKEN=token).status_code == 200
    assert c.delete(f"{URL}?pedido={PEDIDO}", HTTP_X_LECTURA_TOKEN=token).status_code == 204
    assert c.get(URL, HTTP_X_LECTURA_TOKEN=token).status_code == 404


def test_delete_con_el_pedido_en_el_cuerpo():
    c = APIClient()
    token = _post(c).json()["token"]
    r = c.delete(URL, {"pedido": PEDIDO}, format="json", HTTP_X_LECTURA_TOKEN=token)
    assert r.status_code == 204
    assert c.get(URL, HTTP_X_LECTURA_TOKEN=token).status_code == 404


def test_delete_idempotente_y_de_otro_pedido_404():
    c = APIClient()
    token = _post(c).json()["token"]
    assert c.delete(f"{URL}?pedido={OTRO}", HTTP_X_LECTURA_TOKEN=token).status_code == 404
    assert c.get(URL, HTTP_X_LECTURA_TOKEN=token).status_code == 200
    assert c.delete(f"{URL}?pedido={PEDIDO}", HTTP_X_LECTURA_TOKEN=token).status_code == 204
    assert c.delete(f"{URL}?pedido={PEDIDO}", HTTP_X_LECTURA_TOKEN=token).status_code == 404


@pytest.mark.parametrize("query", ["", "?pedido=no-es-un-uuid"])
def test_delete_sin_token_o_pedido_invalido(query):
    c = APIClient()
    token = _post(c).json()["token"]
    assert c.delete(f"{URL}?pedido={PEDIDO}").status_code == 404
    r = c.delete(f"{URL}{query}", HTTP_X_LECTURA_TOKEN=token)
    assert r.status_code == 400 and r.json()["motivo"] == "datos"


def test_post_del_mismo_pedido_con_la_lista_sin_acusar_202_lista():
    c = APIClient()
    token = _post(c).json()["token"]
    r = _post(c, token)
    assert r.status_code == 202 and r.json() == {"token": token, "estado": "lista"}


def test_datos_invalidos_400():
    r = APIClient().post(URL, {"lang": "es"}, format="json")
    assert r.status_code == 400 and r.json()["motivo"] == "datos"


def test_idioma_invalido_400():
    assert _post(APIClient(), lang="fr").status_code == 400


@pytest.mark.parametrize("extra", [{"date": 123}, {"lat": [1]}, {"lang": []}, {"lang": {"a": 1}}])
def test_valores_de_tipo_equivocado_400(extra):
    r = _post(APIClient(), **extra)
    assert r.status_code == 400 and r.json()["motivo"] == "datos"


def test_cuerpo_que_no_es_objeto_400():
    # Lo rechaza antes el parser del proyecto ({"detail": ...}, sin «motivo»).
    assert APIClient().post(URL, [1, 2], format="json").status_code == 400


def test_trato_invalido_400():
    assert _post(APIClient(), trato="otro").status_code == 400


def test_usado_409():
    c = APIClient()
    token = _post(c).json()["token"]
    c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    c.delete(f"{URL}?pedido={PEDIDO}", HTTP_X_LECTURA_TOKEN=token)
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


@pytest.mark.parametrize("valor", [None, "", 123, "no-es-un-uuid", "A" * 36, "1" * 37, ["x"]])
def test_pedido_invalido_o_ausente_400(valor):
    extra = {} if valor is None else {"pedido": valor}
    datos = {**CARTA, "lang": "es", **extra}
    r = APIClient().post(URL, datos, format="json")
    assert r.status_code == 400 and r.json()["motivo"] == "datos"


def test_otro_pedido_mientras_genera_409_y_el_mismo_202(monkeypatch):
    lanzados = []
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: lanzados.append(a))
    c = APIClient()
    token = _post(c).json()["token"]
    r = _post(c, token, pedido=OTRO)
    assert r.status_code == 409 and r.json()["motivo"] == "usado"
    assert _post(c, token).status_code == 202
    assert len(lanzados) == 1
    g = c.get(URL, HTTP_X_LECTURA_TOKEN=token)
    assert g.json() == {"estado": "generando", "pedido": PEDIDO}
