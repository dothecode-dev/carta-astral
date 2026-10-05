"""Lo que Bing dice del sitio, para el informe diario.

Lo que se prueba: que se arme la ventana de 7 días contra los 7 anteriores, que
la fecha de Microsoft (`/Date(ms)/`) se lea bien, que sin clave se diga en el
mail en vez de romperlo, y que la clave NUNCA aparezca en un log ni en el mail.
"""

import datetime

import pytest

from api import bing
from api import informe_actividad as informe

pytestmark = pytest.mark.django_db

HOY = datetime.date(2026, 10, 10)


def _ms(d: datetime.date) -> str:
    """El formato de fecha de la API de Bing: `/Date(1760054400000)/`."""
    epoch = datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)
    return f"/Date({int(epoch.timestamp() * 1000)})/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.BING_WEBMASTER_API_KEY = "clave-de-prueba-no-real"
    settings.BING_SITE_URL = "https://astraguia.com/"


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise bing.httpx.HTTPStatusError("error", request=None, response=None)

    def json(self):
        return {"d": self._body}


@pytest.fixture
def api(monkeypatch):
    """Una API de Bing de mentira que anota qué se le pidió."""
    pedidos: list[dict] = []
    datos = {
        "GetRankAndTrafficStats": [
            # Ventana actual (7 días hasta HOY-1): 3 días con actividad.
            {"Date": _ms(HOY - datetime.timedelta(days=1)), "Clicks": 2, "Impressions": 40},
            {"Date": _ms(HOY - datetime.timedelta(days=3)), "Clicks": 1, "Impressions": 25},
            {"Date": _ms(HOY - datetime.timedelta(days=6)), "Clicks": 0, "Impressions": 10},
            # Ventana previa (los 7 anteriores).
            {"Date": _ms(HOY - datetime.timedelta(days=9)), "Clicks": 5, "Impressions": 30},
            # Más vieja que las dos ventanas: no cuenta.
            {"Date": _ms(HOY - datetime.timedelta(days=40)), "Clicks": 99, "Impressions": 999},
        ],
        "GetQueryStats": [
            {"Query": "carta natal gratis", "Clicks": 2, "Impressions": 30, "AvgImpressionPosition": 8},
            {"Query": "luna hoy", "Clicks": 1, "Impressions": 70, "AvgImpressionPosition": 14},
        ],
        "GetPageStats": [
            {"Query": "https://astraguia.com/es/cielo-hoy", "Clicks": 1, "Impressions": 70},
        ],
    }

    def get(url, **kwargs):
        metodo = url.rsplit("/", 1)[-1]
        pedidos.append({"metodo": metodo, "params": kwargs.get("params", {})})
        return _Resp(body=datos[metodo])

    monkeypatch.setattr(bing.httpx, "get", get)
    return pedidos


def test_suma_la_ventana_actual_y_la_previa_por_separado(api):
    r = bing.busquedas(hoy=HOY)

    assert r["clics"] == 3
    assert r["impresiones"] == 75
    assert r["previo"] == {"clics": 5, "impresiones": 30}


def test_lo_mas_viejo_que_las_dos_ventanas_no_cuenta(api):
    r = bing.busquedas(hoy=HOY)

    assert r["clics"] + r["previo"]["clics"] == 8  # sin los 99 de hace 40 días


def test_cuenta_los_dias_con_actividad_para_leer_un_cero(api):
    # Mismo criterio que PostHog: a esta escala el promedio engaña, cuántos días
    # tuvieron algo es lo que dice si un cero es raro.
    r = bing.busquedas(hoy=HOY)

    assert r["dias_con_actividad"] == 3


def test_trae_las_consultas_y_las_paginas(api):
    r = bing.busquedas(hoy=HOY)

    assert r["consultas"][0] == {
        "consulta": "carta natal gratis", "impresiones": 30, "clics": 2, "posicion": 8.0,
    }
    assert r["paginas"] == [
        {"pagina": "https://astraguia.com/es/cielo-hoy", "impresiones": 70, "clics": 1},
    ]


def test_pide_siempre_el_sitio_configurado(api):
    bing.busquedas(hoy=HOY)

    assert {p["params"]["siteUrl"] for p in api} == {"https://astraguia.com/"}


def test_sin_clave_es_una_fuente_caida_y_no_sale_a_la_red(settings, monkeypatch):
    settings.BING_WEBMASTER_API_KEY = ""
    monkeypatch.setattr(bing.httpx, "get", lambda *a, **k: pytest.fail("no debía salir"))

    with pytest.raises(informe.FuenteCaida, match="BING_WEBMASTER_API_KEY"):
        bing.busquedas(hoy=HOY)


def test_una_respuesta_de_error_es_una_fuente_caida(monkeypatch):
    monkeypatch.setattr(bing.httpx, "get", lambda *a, **k: _Resp(status=403))

    with pytest.raises(informe.FuenteCaida):
        bing.busquedas(hoy=HOY)


def test_el_error_no_filtra_la_clave(monkeypatch):
    # httpx pone la URL completa en sus excepciones, y la clave va en la URL.
    def explota(url, **kwargs):
        raise bing.httpx.ConnectError(f"no conecta a {url}?apikey={kwargs['params']['apikey']}")

    monkeypatch.setattr(bing.httpx, "get", explota)

    with pytest.raises(informe.FuenteCaida) as exc:
        bing.busquedas(hoy=HOY)

    assert "clave-de-prueba-no-real" not in str(exc.value)


def test_el_mail_trae_la_seccion_de_bing_y_no_la_clave(api, settings, monkeypatch):
    settings.RESEND_API_KEY = "re_de_prueba"
    settings.INFORME_DESTINO = "alguien@example.com"
    settings.MAIL_FROM = "info@astraguia.com"
    settings.ANTHROPIC_API_KEY = ""
    settings.POSTHOG_PERSONAL_API_KEY = ""
    settings.GSC_REFRESH_TOKEN = ""
    enviados = []

    class _Mail:
        status_code = 200

        def raise_for_status(self):
            pass

    def post(url, **kwargs):
        if url == "https://api.resend.com/emails":
            enviados.append(kwargs["json"]["html"])
        return _Mail()

    monkeypatch.setattr(informe.httpx, "post", post)
    monkeypatch.setattr(bing, "busquedas", lambda *a, **k: _fijo())
    informe.generar_y_enviar()

    html = enviados[0]
    assert "En Bing" in html
    assert "carta natal gratis" in html
    assert "clave-de-prueba-no-real" not in html


def _fijo() -> dict:
    return {
        "ventana": "2026-10-03 a 2026-10-09",
        "clics": 3,
        "impresiones": 75,
        "previo": {"clics": 5, "impresiones": 30},
        "dias_con_actividad": 3,
        "consultas": [
            {"consulta": "carta natal gratis", "impresiones": 30, "clics": 2, "posicion": 8.0},
        ],
        "paginas": [],
    }
