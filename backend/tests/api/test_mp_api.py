"""Cliente HTTP de Mercado Pago: contra `httpx.MockTransport`, sin red."""

import json
import logging

import httpx
import pytest

from api.pasarelas import mercadopago_api as mp

TOKEN = "APP_USR-secreto-que-no-debe-filtrarse"


class _Pedidos(list):
    responder = None


@pytest.fixture
def transporte(settings, monkeypatch):
    """Instala un `_cliente()` falso; devuelve la lista de pedidos vistos."""
    settings.MP_ACCESS_TOKEN = TOKEN
    pedidos = _Pedidos()
    respuesta = {"handler": lambda req: httpx.Response(200, json={})}

    def handler(req: httpx.Request) -> httpx.Response:
        pedidos.append(req)
        return respuesta["handler"](req)

    def cliente():
        return httpx.Client(
            base_url=mp.BASE_URL,
            headers={"Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}"},
            transport=httpx.MockTransport(handler),
        )

    monkeypatch.setattr(mp, "_cliente", cliente)
    pedidos.responder = lambda h: respuesta.update(handler=h)
    return pedidos


def test_sin_token_levanta_no_configurado(settings):
    settings.MP_ACCESS_TOKEN = ""
    with pytest.raises(mp.MPNoConfigurado):
        mp.obtener_pago("1")


def test_crear_preferencia_manda_bearer_y_json(transporte):
    transporte.responder(
        lambda req: httpx.Response(201, json={"id": "p1", "init_point": "https://mp/x"})
    )
    r = mp.crear_preferencia({"items": [{"title": "Informe"}]})
    assert r["init_point"] == "https://mp/x"
    req = transporte[0]
    assert req.method == "POST"
    assert req.url.path == "/checkout/preferences"
    assert req.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(req.content) == {"items": [{"title": "Informe"}]}


def test_reembolsar_manda_idempotency_key(transporte):
    transporte.responder(lambda req: httpx.Response(201, json={"id": 9}))
    mp.reembolsar("123", "clave-1")
    req = transporte[0]
    assert req.method == "POST"
    assert req.url.path == "/v1/payments/123/refunds"
    assert req.headers["X-Idempotency-Key"] == "clave-1"
    assert json.loads(req.content) == {}


@pytest.mark.parametrize("status", [400, 404, 500, 503])
def test_status_4xx_y_5xx_levantan_mperror_con_status(transporte, status):
    transporte.responder(lambda req: httpx.Response(status, json={"message": "no"}))
    with pytest.raises(mp.MPError) as info:
        mp.obtener_pago("1")
    assert info.value.status == status
    assert TOKEN not in str(info.value)


def test_timeout_levanta_mperror_sin_status(transporte, caplog):
    def boom(req):
        raise httpx.ReadTimeout("lento", request=req)

    transporte.responder(boom)
    with caplog.at_level(logging.DEBUG), pytest.raises(mp.MPError) as info:
        mp.obtener_contracargo("c1")
    assert info.value.status is None
    assert TOKEN not in str(info.value)
    assert TOKEN not in caplog.text


def test_buscar_pagos_devuelve_results(transporte):
    transporte.responder(lambda req: httpx.Response(200, json={"results": [{"id": 1}]}))
    assert mp.buscar_pagos("ref-1") == [{"id": 1}]
    assert transporte[0].url.path == "/v1/payments/search"
    assert transporte[0].url.params["external_reference"] == "ref-1"


_FUNCIONES_CON_ID = [
    mp.obtener_pago,
    mp.obtener_contracargo,
    lambda i: mp.reembolsar(i, "k"),
]


@pytest.mark.parametrize("funcion", _FUNCIONES_CON_ID)
@pytest.mark.parametrize("malicioso", [".", "..", "1/refunds", "../x", "1?a=b", ""])
def test_id_invalido_levanta_sin_hacer_pedido(transporte, funcion, malicioso):
    with pytest.raises(mp.MPError) as info:
        funcion(malicioso)
    assert info.value.status is None
    assert len(transporte) == 0


@pytest.mark.parametrize("funcion", _FUNCIONES_CON_ID)
def test_id_numerico_normal_funciona(transporte, funcion):
    transporte.responder(lambda req: httpx.Response(200, json={}))
    funcion("184963579792")
    assert "/184963579792" in transporte[0].url.path


def test_json_que_no_es_objeto_levanta_mperror(transporte):
    transporte.responder(lambda req: httpx.Response(200, json=[1, 2]))
    with pytest.raises(mp.MPError) as info:
        mp.buscar_pagos("ref")
    assert info.value.status == 200


def test_2xx_que_no_es_json_levanta_mperror(transporte):
    transporte.responder(lambda req: httpx.Response(200, content=b"<html>"))
    with pytest.raises(mp.MPError) as info:
        mp.obtener_pago("1")
    assert info.value.status == 200
