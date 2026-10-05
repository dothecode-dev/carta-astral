"""Qué páginas del sitemap tiene Google indexadas, para el informe diario.

Lo que importa: que lea las URLs del sitemap y no de una lista a mano —así una
nota nueva entra sola—, que una URL que falla no se lleve a las demás, y que
sin credenciales se diga en el mail en vez de romperlo.
"""

import pytest

from api import indexacion
from api import informe_actividad as informe

pytestmark = pytest.mark.django_db

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://astraguia.com/es</loc></url>
<url><loc>https://astraguia.com/es/cielo-hoy</loc></url>
<url><loc>https://astraguia.com/en/sky-today</loc></url>
<url><loc>https://astraguia.com/es</loc></url>
</urlset>"""


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.GSC_CLIENT_ID = "id"
    settings.GSC_CLIENT_SECRET = "secreto"
    settings.GSC_REFRESH_TOKEN = "refresh"
    settings.GSC_SITE_URL = "sc-domain:astraguia.com"
    settings.SITEMAP_URL = "https://astraguia.com/sitemap.xml"


class _Resp:
    def __init__(self, status=200, json=None, text=""):
        self.status_code = status
        self._json = json or {}
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise indexacion.httpx.HTTPStatusError("error", request=None, response=None)

    def json(self):
        return self._json


@pytest.fixture
def google(monkeypatch):
    """Sitemap, token y una respuesta de inspección por URL."""
    estados = {
        "https://astraguia.com/es": ("PASS", "Submitted and indexed"),
        "https://astraguia.com/es/cielo-hoy": ("NEUTRAL", "URL is unknown to Google"),
        "https://astraguia.com/en/sky-today": ("NEUTRAL", "Discovered - currently not indexed"),
    }
    inspeccionadas: list[str] = []

    def get(url, **kwargs):
        assert url == "https://astraguia.com/sitemap.xml"
        return _Resp(text=SITEMAP)

    def post(url, **kwargs):
        if url.startswith("https://oauth2"):
            return _Resp(json={"access_token": "tok"})
        cuerpo = kwargs["json"]
        assert cuerpo["siteUrl"] == "sc-domain:astraguia.com"
        inspeccionadas.append(cuerpo["inspectionUrl"])
        veredicto, estado = estados[cuerpo["inspectionUrl"]]
        return _Resp(json={"inspectionResult": {"indexStatusResult": {
            "verdict": veredicto, "coverageState": estado,
        }}})

    monkeypatch.setattr(indexacion.httpx, "get", get)
    monkeypatch.setattr(indexacion.httpx, "post", post)
    monkeypatch.setattr(informe.httpx, "post", post)
    return inspeccionadas


def test_inspecciona_cada_url_del_sitemap_una_sola_vez(google):
    indexacion.estado_de_indexacion()

    assert sorted(google) == [
        "https://astraguia.com/en/sky-today",
        "https://astraguia.com/es",
        "https://astraguia.com/es/cielo-hoy",
    ]


def test_cuenta_las_indexadas_y_lista_las_que_faltan_con_su_estado(google):
    estado = indexacion.estado_de_indexacion()

    assert estado["total"] == 3
    assert estado["indexadas"] == 1
    assert estado["sin_indexar"] == [
        {"url": "https://astraguia.com/en/sky-today", "estado": "Discovered - currently not indexed"},
        {"url": "https://astraguia.com/es/cielo-hoy", "estado": "URL is unknown to Google"},
    ]


def test_una_url_que_falla_no_se_lleva_a_las_demas(google, monkeypatch):
    post_original = indexacion.httpx.post

    def post(url, **kwargs):
        if kwargs.get("json", {}).get("inspectionUrl") == "https://astraguia.com/es/cielo-hoy":
            return _Resp(status=500)
        return post_original(url, **kwargs)

    monkeypatch.setattr(indexacion.httpx, "post", post)
    estado = indexacion.estado_de_indexacion()

    assert estado["indexadas"] == 1
    assert {"url": "https://astraguia.com/es/cielo-hoy", "estado": "no se pudo inspeccionar"} in (
        estado["sin_indexar"]
    )


def test_sin_credenciales_es_una_fuente_caida(settings):
    settings.GSC_REFRESH_TOKEN = ""

    with pytest.raises(informe.FuenteCaida):
        indexacion.estado_de_indexacion()


def test_el_mail_lista_las_paginas_sin_indexar(google, settings, monkeypatch):
    settings.RESEND_API_KEY = "re_de_prueba"
    settings.INFORME_DESTINO = "alguien@example.com"
    settings.ANTHROPIC_API_KEY = ""
    settings.POSTHOG_PERSONAL_API_KEY = ""
    enviados = []
    post_google = informe.httpx.post

    def post(url, **kwargs):
        if url == "https://api.resend.com/emails":
            enviados.append(kwargs["json"]["html"])
            return _Resp()
        return post_google(url, **kwargs)

    monkeypatch.setattr(informe.httpx, "post", post)
    informe.generar_y_enviar()

    html = enviados[0]
    assert "1 de 3" in html
    assert "https://astraguia.com/es/cielo-hoy" in html
    assert "URL is unknown to Google" in html
