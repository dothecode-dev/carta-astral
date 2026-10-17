"""De dónde viene la gente que calcula su carta, contado en el servidor sin cookies.

La web manda `procedencia: {utm_source, referrer, zona}` junto con la carta. El
servidor sólo guarda dos contadores agregados por día —canal y zona horaria—,
nunca el valor crudo: el referrer y la zona se reducen a una lista cerrada."""

import pytest
from django.utils import timezone

from api import conteo
from api.models import ConteoProcedencia

pytestmark = pytest.mark.django_db

PREVIEW = "/api/charts/preview/"
DATOS = {"date": "1990-05-10", "time": "14:30", "lat": -34.6, "lng": -58.4}


@pytest.mark.parametrize(("utm", "referrer", "canal"), [
    ("google", "", "google_ads"),
    ("google", "https://www.google.com/", "google_ads"),
    ("", "https://www.google.com.ar/", "google"),
    ("", "https://www.bing.com/search?q=x", "otros_buscadores"),
    ("", "https://duckduckgo.com/", "otros_buscadores"),
    ("", "https://l.instagram.com/", "redes"),
    ("", "https://www.facebook.com/", "redes"),
    ("", "https://t.co/abc", "redes"),
    ("", "https://blog.ejemplo.com/nota", "otro_sitio"),
    ("", "", "directo"),
    ("newsletter", "", "otra_campana"),
    (None, None, "directo"),
    ("", "http://[", "otro_sitio"),
    (123, ["x"], "directo"),
])
def test_el_canal_sale_de_una_lista_cerrada(utm, referrer, canal):
    assert conteo.canal_de(utm, referrer) == canal


def test_la_zona_se_reduce_a_un_lugar_legible():
    assert conteo.lugar_de_zona("America/Bogota") == "Bogotá"
    assert conteo.lugar_de_zona("America/Argentina/Cordoba") == "Argentina"
    assert conteo.lugar_de_zona("America/Argentina/Buenos_Aires") == "Argentina"
    assert conteo.lugar_de_zona("Europe/Madrid") == "Madrid"
    assert conteo.lugar_de_zona("America/Mexico_City") == "Mexico City"


def test_una_zona_inventada_no_entra_como_lugar():
    # El valor viene del navegador: cualquiera puede mandar cualquier cosa.
    assert conteo.lugar_de_zona("<script>") == "desconocida"
    assert conteo.lugar_de_zona("x" * 500) == "desconocida"
    assert conteo.lugar_de_zona(None) == "desconocida"


def test_la_vista_previa_cuenta_canal_y_lugar(client):
    cuerpo = {**DATOS, "procedencia": {"utm_source": "google", "referrer": "", "zona": "America/Bogota"}}
    assert client.post(PREVIEW, cuerpo, content_type="application/json").status_code == 200
    hoy = timezone.now().date()
    assert ConteoProcedencia.objects.get(fecha=hoy, tipo="canal", valor="google_ads").cantidad == 1
    assert ConteoProcedencia.objects.get(fecha=hoy, tipo="lugar", valor="Bogotá").cantidad == 1


def test_sin_procedencia_cuenta_directo_y_desconocida(client):
    assert client.post(PREVIEW, DATOS, content_type="application/json").status_code == 200
    assert ConteoProcedencia.objects.get(tipo="canal").valor == "directo"
    assert ConteoProcedencia.objects.get(tipo="lugar").valor == "desconocida"


def test_una_procedencia_rara_no_rompe_la_carta(client):
    cuerpo = {**DATOS, "procedencia": "no soy un objeto"}
    assert client.post(PREVIEW, cuerpo, content_type="application/json").status_code == 200
    assert ConteoProcedencia.objects.get(tipo="canal").valor == "directo"


def test_crear_una_carta_con_cuenta_tambien_cuenta_la_procedencia(account_client):
    cuerpo = {**DATOS, "procedencia": {"referrer": "https://www.google.com/", "zona": "Europe/Madrid"}}
    assert account_client.post("/api/charts/", cuerpo, format="json").status_code == 201
    assert ConteoProcedencia.objects.get(tipo="canal").valor == "google"


def test_la_serie_de_procedencia_trae_los_mas_frecuentes():
    hoy = timezone.now().date()
    for valor, n in (("google_ads", 9), ("directo", 3), ("google", 1)):
        ConteoProcedencia.objects.create(fecha=hoy, tipo="canal", valor=valor, cantidad=n)
    s = conteo.serie_procedencia("canal", dias=2, top=2)
    assert s["fechas"][-1] == str(hoy)
    assert [nombre for nombre, _ in s["series"]] == ["google_ads", "directo"]
    assert s["series"][0][1] == [0, 9]
