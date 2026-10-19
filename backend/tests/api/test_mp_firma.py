"""Verificación de la firma del webhook de Mercado Pago."""

import time

import pytest

from api.pasarelas.mercadopago_firma import verificar
from tests.api.mp_firma import SECRETO, firmar

REQ = "5f0c7f3e-1b2a-4c3d-9e8f-0a1b2c3d4e5f"


def test_firma_valida():
    h = firmar("123456", REQ)
    assert verificar(h, REQ, "123456", SECRETO) is True


def test_cuerpo_de_otro_id_no_valida():
    h = firmar("123456", REQ)
    assert verificar(h, REQ, "999999", SECRETO) is False


def test_secreto_distinto_no_valida():
    h = firmar("123456", REQ)
    assert verificar(h, REQ, "123456", "otro") is False


def test_request_id_distinto_no_valida():
    h = firmar("123456", REQ)
    assert verificar(h, "otro-request", "123456", SECRETO) is False


@pytest.mark.parametrize(
    "header",
    [
        "",
        "basura",
        "ts=1792413808",
        "v1=" + "a" * 64,
        "ts=1792413808,v1",
        "ts=1792413808,v1=" + "a" * 64 + ",ts=1792413809",
        "ts=1792413808,v1=" + "a" * 64 + ",v1=" + "b" * 64,
        "ts=1792413808,v1=zzzz",
        "ts=,v1=" + "a" * 64,
        "ts=abc,v1=" + "a" * 64,
        ",,,",
    ],
)
def test_header_mal_formado_es_false(header):
    assert verificar(header, REQ, "123456", SECRETO) is False


def test_header_none_es_false():
    assert verificar(None, REQ, "123456", SECRETO) is False  # type: ignore[arg-type]


def test_sin_request_id_omite_el_par():
    h = firmar("123456", "")
    assert verificar(h, "", "123456", SECRETO) is True
    assert verificar(h, REQ, "123456", SECRETO) is False


def test_sin_data_id_omite_el_par():
    h = firmar("", REQ)
    assert verificar(h, REQ, "", SECRETO) is True


def test_id_en_mayuscula_se_compara_en_minuscula():
    uuid = "AB12CD34-0000-4000-8000-ABCDEF012345"
    h = firmar(uuid.lower(), REQ)
    assert verificar(h, REQ, uuid, SECRETO) is True


def test_ts_viejo_valida():
    tres_dias = int(time.time()) - 3 * 86400
    h = firmar("123456", REQ, ts=tres_dias)
    assert verificar(h, REQ, "123456", SECRETO) is True


def test_secreto_vacio_rechaza():
    h = firmar("123456", REQ, secreto="")
    assert verificar(h, REQ, "123456", "") is False


@pytest.mark.parametrize("data_id,req", [("\ud800", REQ), ("123456", "\ud800")])
def test_surrogate_suelto_es_false_sin_excepcion(data_id, req):
    h = firmar("123456", REQ)
    assert verificar(h, req, data_id, SECRETO) is False


@pytest.mark.parametrize("n", [63, 65])
def test_v1_de_largo_incorrecto_es_false(n):
    assert verificar(f"ts=1,v1={'a' * n}", REQ, "123456", SECRETO) is False


def test_v1_en_mayuscula_se_acepta():
    h = firmar("123456", REQ)
    ts, v1 = h.split(",")
    assert verificar(f"{ts},{v1.upper().replace('V1', 'v1')}", REQ, "123456", SECRETO)


def test_espacios_alrededor_de_las_partes_se_aceptan():
    ts, v1 = firmar("123456", REQ).split(",")
    assert verificar(f"{ts}, {v1}", REQ, "123456", SECRETO) is True
