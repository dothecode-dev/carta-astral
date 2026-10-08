"""Un cuerpo JSON válido que no es un objeto da 400, nunca 500.

`request.data.get(...)` revienta con `AttributeError` si el cuerpo es `[]`,
`null`, `3` o `"x"`: JSON válido, pero no un diccionario. El arreglo es un
único parser (`config.parsers.JSONObjetoParser`) y no un chequeo por vista; estos
tests recorren todas las rutas de escritura que leen `request.data` para que
una vista nueva no pueda reintroducir el 500.

Excluidas a propósito: los webhooks de Stripe y Resend (leen `request.body`
crudo, nunca `request.data`; su firma se verifica sobre los bytes) y
`auth/logout` (no lee el cuerpo) y el webhook de RevenueCat, que contesta 200
"ignored" a un cuerpo que no es objeto a propósito (ver su vista y
`test_revenuecat_webhook.py`).
"""

import io
import json

import pytest
from rest_framework.exceptions import ParseError
from rest_framework.test import APIClient


pytestmark = pytest.mark.django_db

CUERPOS_NO_OBJETO = ["[]", "null", "3", '"x"', "[1, 2]", "true"]

PAYLOAD_CARTA = {
    "name": "Ceci", "date": "1976-05-31", "time": "19:30", "time_known": True,
    "lat": -34.516, "lng": -58.5, "place_label": "Florida, Buenos Aires, AR",
}


def _enviar(client, metodo, url, cuerpo, **extra):
    return getattr(client, metodo)(
        url, data=cuerpo, content_type="application/json", **extra
    )


# (metodo, url, requiere_sesion). Sacadas de api/urls.py: toda ruta que
# acepta POST/PATCH/PUT y lee `request.data`.
RUTAS_PUBLICAS = [
    ("post", "/api/charts/preview/"),
    ("post", "/api/vinculo/preview/"),
    ("post", "/api/geocode/"),
    ("post", "/api/checkout/anonimo/"),
    ("post", "/api/checkout/anonimo/canjear/"),
    ("post", "/api/auth/email/codigo"),
    ("post", "/api/auth/email"),
    ("post", "/api/auth/google"),
    ("post", "/api/auth/apple"),
]

RUTAS_CON_SESION = [
    ("post", "/api/charts/"),
    ("post", "/api/checkout/"),
    ("patch", "/api/charts/{uuid}/"),
    ("post", "/api/charts/{uuid}/interpretation/"),
    ("post", "/api/charts/{uuid}/pdf/"),
]


@pytest.fixture
def apps_encendidas(settings):
    """Las superficies que el repo tiene apagadas por flag: sin encenderlas la
    vista contestaría 503/404 antes de leer el cuerpo y el test no probaría
    nada."""
    settings.APP_AUTH_ENABLED = True
    settings.VINCULO_PREVIEW_ENABLED = True


@pytest.mark.parametrize("cuerpo", CUERPOS_NO_OBJETO)
@pytest.mark.parametrize("metodo,url", RUTAS_PUBLICAS)
def test_ruta_publica_con_cuerpo_que_no_es_objeto_da_400(
    apps_encendidas, metodo, url, cuerpo
):
    r = _enviar(APIClient(), metodo, url, cuerpo)
    assert r.status_code == 400, (url, cuerpo, r.status_code, r.content[:200])


@pytest.mark.parametrize("cuerpo", CUERPOS_NO_OBJETO)
@pytest.mark.parametrize("metodo,url", RUTAS_CON_SESION)
def test_ruta_con_sesion_y_cuerpo_que_no_es_objeto_da_400(
    account_client, chart_de_la_cuenta, metodo, url, cuerpo
):
    url = url.format(uuid=chart_de_la_cuenta.uuid)
    r = _enviar(account_client, metodo, url, cuerpo)
    assert r.status_code == 400, (url, cuerpo, r.status_code, r.content[:200])


@pytest.fixture
def chart_de_la_cuenta(make_chart, account_client):
    return make_chart(account=account_client.account)


def test_el_400_dice_por_que():
    r = _enviar(APIClient(), "post", "/api/charts/preview/", "[]")
    assert r.status_code == 400
    assert "objeto JSON" in json.dumps(r.json(), ensure_ascii=False)


# --- El parser solo ---------------------------------------------------------

def _parsear(texto):
    from config.parsers import JSONObjetoParser

    return JSONObjetoParser().parse(
        io.BytesIO(texto.encode()), "application/json", {}
    )


@pytest.mark.parametrize("cuerpo", CUERPOS_NO_OBJETO)
def test_parser_rechaza_lo_que_no_es_objeto(cuerpo):
    with pytest.raises(ParseError):
        _parsear(cuerpo)


def test_parser_acepta_objetos():
    assert _parsear("{}") == {}
    assert _parsear('{"a": [1, 2], "b": null}') == {"a": [1, 2], "b": None}


def test_parser_sigue_rechazando_json_roto_con_parse_error():
    with pytest.raises(ParseError):
        _parsear("{")


# --- Lo que andaba sigue andando -------------------------------------------

def test_preview_con_objeto_vacio_sigue_dando_400_de_datos_invalidos():
    r = APIClient().post("/api/charts/preview/", {}, format="json")
    assert r.status_code == 400
    assert "error" in r.json()


def test_preview_con_objeto_valido_sigue_dando_la_carta():
    r = APIClient().post("/api/charts/preview/", PAYLOAD_CARTA, format="json")
    assert r.status_code == 200, r.content[:200]
    assert r.json()["data"]["placements"]
