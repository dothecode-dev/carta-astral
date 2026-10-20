import httpx
import pytest

from api import informe_actividad


def _rates(brl):
    return lambda url, timeout=None: httpx.Response(
        200, json={"result": "success", "rates": {"BRL": brl}}, request=httpx.Request("GET", url)
    )


@pytest.mark.catalogo_real
def test_mide_cuanto_vale_el_informe_en_reales_al_cambio_de_hoy(monkeypatch):
    monkeypatch.setattr(informe_actividad.httpx, "get", _rates(5.0))

    datos = informe_actividad.cambio_brl()

    assert datos["informe_brl_en_usd"] == 19.98
    assert datos["alerta"] is False


@pytest.mark.catalogo_real
def test_avisa_si_se_aleja_mas_del_15_por_ciento(monkeypatch):
    monkeypatch.setattr(informe_actividad.httpx, "get", _rates(6.5))  # 99,90 / 6,5 = 15,37 → −23 %

    assert informe_actividad.cambio_brl()["alerta"] is True


def test_sin_respuesta_es_una_fuente_caida(monkeypatch):
    def get(url, timeout=None):
        raise httpx.ConnectError("x", request=httpx.Request("GET", url))

    monkeypatch.setattr(informe_actividad.httpx, "get", get)

    with pytest.raises(informe_actividad.FuenteCaida):
        informe_actividad.cambio_brl()


@pytest.mark.parametrize("brl", ["NaN", 0, -1])
def test_un_cambio_que_no_es_positivo_es_una_fuente_caida(monkeypatch, brl):
    monkeypatch.setattr(informe_actividad.httpx, "get", _rates(brl))

    with pytest.raises(informe_actividad.FuenteCaida):
        informe_actividad.cambio_brl()
