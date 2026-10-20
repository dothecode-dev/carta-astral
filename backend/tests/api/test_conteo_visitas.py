"""Visitas y países, contados en el servidor sin cookies (20-10-2026).

Hasta acá el servidor sólo contaba cartas calculadas: no había visitas ni
países. El país sale de la IP con la base de MaxMind que ya decide la moneda,
y lo único que se guarda es el código del país en un contador del día: la IP
no se guarda en ningún lado.
"""

import datetime

import pytest
from django.utils import timezone

from api import conteo, geo
from api.models import ConteoDiario, ConteoProcedencia, PasarelaCheckout

pytestmark = pytest.mark.django_db

URL = "/api/conteo/visita/"
DESDE_ADS = {"utm_source": "google", "gclid": False, "referrer": "", "zona": "America/Argentina/Cordoba"}


@pytest.fixture(autouse=True)
def _cache_limpia(django_cache_cleared):
    """El techo por IP vive en la caché: sin limpiarla, los tests se lo gastan entre sí."""


@pytest.fixture
def desde_argentina(monkeypatch):
    monkeypatch.setattr(geo, "pais_de", lambda ip: "AR")


def _proc(tipo):
    hoy = timezone.now().date()
    return {f.valor: f.cantidad for f in ConteoProcedencia.objects.filter(fecha=hoy, tipo=tipo)}


def _visitar(client, **cuerpo):
    return client.post(URL, data=cuerpo, content_type="application/json")


def test_una_visita_cuenta_pais_seccion_y_canal(client, desde_argentina):
    r = _visitar(client, seccion="precios", procedencia=DESDE_ADS)

    assert r.status_code == 204
    assert ConteoDiario.objects.get(evento="visita").cantidad == 1
    assert _proc("visita_pais") == {"AR": 1}
    assert _proc("visita_seccion") == {"precios": 1}
    assert _proc("visita_canal") == {"google_ads": 1}


def test_sin_pais_conocido_cuenta_como_desconocido(client, monkeypatch):
    monkeypatch.setattr(geo, "pais_de", lambda ip: None)

    _visitar(client, seccion="inicio")

    assert _proc("visita_pais") == {"??": 1}
    assert _proc("visita_canal") == {"directo": 1}


@pytest.mark.parametrize("seccion", ["", "cualquiera", None, ["precios"], "x" * 200])
def test_una_seccion_fuera_de_la_lista_no_se_cuenta(client, desde_argentina, seccion):
    r = _visitar(client, seccion=seccion)

    assert r.status_code == 400
    assert not ConteoDiario.objects.exists() and not ConteoProcedencia.objects.exists()


def test_es_publico_y_tiene_techo_por_ip():
    from api.conteo_api import ConteoVisitaView

    assert ConteoVisitaView.authentication_classes == []
    assert ConteoVisitaView.throttle_scope == "conteo"


def test_calcular_una_carta_tambien_cuenta_el_pais(client, desde_argentina):
    datos = {"date": "1990-05-10", "time": "14:30", "lat": -34.6, "lng": -58.4, "procedencia": DESDE_ADS}

    assert client.post("/api/charts/preview/", datos, content_type="application/json").status_code == 200

    assert _proc("pais") == {"AR": 1}
    assert _proc("lugar") == {"Argentina": 1}


def test_el_tablero_trae_la_historia_desde_el_primer_dato():
    hoy = timezone.now().date()
    hace_3 = hoy - datetime.timedelta(days=3)
    ConteoDiario.objects.create(fecha=hace_3, evento="visita", cantidad=10)
    ConteoDiario.objects.create(fecha=hoy, evento="carta_calculada", cantidad=4)
    ConteoProcedencia.objects.create(fecha=hace_3, tipo="visita_pais", valor="BR", cantidad=2)
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.MERCADOPAGO, checkout_id="mp_" + "1" * 32, codigo_producto="informe_natal",
        moneda="ars", precio_centavos=2_500_000, acreditado_at=timezone.now(),
    )

    t = conteo.tablero()

    assert t["fechas"][0] == str(hace_3) and t["fechas"][-1] == str(hoy) and len(t["fechas"]) == 4
    assert t["eventos"]["visita"] == [10, 0, 0, 0]
    assert t["eventos"]["carta_calculada"] == [0, 0, 0, 4]
    assert t["eventos"]["compra_pagada"] == [0, 0, 0, 1]
    assert t["ingresos"]["ars"] == [0, 0, 0, 2_500_000]
    assert t["procedencia"]["visita_pais"]["BR"] == [2, 0, 0, 0]


def test_el_tablero_vacio_no_rompe():
    t = conteo.tablero()

    assert t["fechas"] == [str(timezone.now().date())]
