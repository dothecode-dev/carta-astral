"""Lo que hace quien calculó su carta sin cuenta, contado en el servidor (20-10-2026).

Entre «calculó la carta» y «abrió un pago» no se medía nada: con ~200 cartas y
0 pagos no se sabía si nadie apretaba comprar o si se frenaban en el mail que
se pide en pesos. Mismo trato que `ConteoDiario`: un contador por día y
evento, sin cookies ni nada de quién fue.
"""

import pytest
from django.utils import timezone

from api import conteo
from api.models import ConteoDiario

pytestmark = pytest.mark.django_db

URL = "/api/conteo/teaser/"


@pytest.fixture(autouse=True)
def _cache_limpia(django_cache_cleared):
    """El techo por IP vive en la caché: sin limpiarla, los tests se lo gastan entre sí."""


def _contado(evento):
    fila = ConteoDiario.objects.filter(fecha=timezone.now().date(), evento=evento).first()
    return fila.cantidad if fila else 0


def _mandar(client, **cuerpo):
    return client.post(URL, data=cuerpo, content_type="application/json")


@pytest.mark.parametrize("evento", ["datos_abiertos", "cierre_visto", "mail_enviado", "volver"])
def test_cada_paso_suma_su_contador(client, evento):
    r = _mandar(client, evento=evento)

    assert r.status_code == 204
    assert _contado(f"teaser_{evento}") == 1


@pytest.mark.parametrize("donde", ["arriba", "cierre"])
@pytest.mark.parametrize("moneda", ["usd", "brl", "ars"])
def test_un_clic_en_comprar_cuenta_donde_y_en_que_moneda(client, donde, moneda):
    r = _mandar(client, evento=f"clic_{donde}", moneda=moneda)

    assert r.status_code == 204
    assert _contado(f"teaser_clic_{donde}") == 1
    assert _contado(f"teaser_clic_{moneda}") == 1


def test_un_clic_sin_moneda_cuenta_igual_la_posicion(client):
    _mandar(client, evento="clic_arriba")

    assert _contado("teaser_clic_arriba") == 1
    assert ConteoDiario.objects.count() == 1


@pytest.mark.parametrize("cuerpo", [
    {"evento": "cualquiera"},
    {"evento": ""},
    {},
    {"evento": ["clic_arriba"]},
    {"evento": "clic_arriba", "moneda": "eur"},
    {"evento": "clic_arriba", "moneda": "USD "},
    {"evento": "teaser_clic_arriba"},
    {"evento": "carta_calculada"},
])
def test_lo_que_no_esta_en_la_lista_no_se_cuenta(client, cuerpo):
    """La lista es cerrada: el navegador no puede inventar contadores ni
    sumarle a los que cuenta el servidor solo (`carta_calculada`)."""
    r = _mandar(client, **cuerpo)

    assert r.status_code == 400
    assert not ConteoDiario.objects.exists()


def test_es_publico_y_tiene_techo_por_ip(settings):
    from api.conteo_api import ConteoTeaserView

    assert ConteoTeaserView.authentication_classes == []
    assert ConteoTeaserView.throttle_scope == "conteo"
    assert "conteo" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]


def test_los_eventos_del_teaser_entran_en_el_resumen_del_informe_diario():
    """`resumen` y `serie` recorren `conteo.EVENTOS`: un evento nuevo llega
    solo a sus datos. El informe diario los nombra uno por uno; el panel del
    admin, recién con su rediseño."""
    for evento in conteo.EVENTOS_TEASER:
        assert evento in conteo.EVENTOS
    assert "teaser_clic_ars" in conteo.resumen()["total"]


def test_los_pasos_y_las_monedas_salen_del_modelo():
    assert set(conteo.PASOS_TEASER) == {
        "datos_abiertos", "cierre_visto", "clic_arriba", "clic_cierre", "mail_enviado", "volver",
    }
    assert set(conteo.MONEDAS_CLIC) == {"usd", "brl", "ars"}
