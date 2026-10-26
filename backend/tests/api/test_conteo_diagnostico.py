"""Lo que faltaba para leer el embudo (22-10-2026).

Con 269 cartas, 184 que llegaron al precio y 0 clics, no se podía saber de qué
fuente venía el tráfico «otra campaña», ni si los pagos del panel eran de
terceros: eran pruebas del dueño. Tres cosas:

- las compras hechas con los mails de `MAILS_DE_PRUEBA` no cuentan como ventas;
- de una campaña con `utm_source` propio se guarda el nombre (acotado);
- los pasos del teaser se separan por canal y por moneda mostrada.
"""

import datetime

import pytest
from django.utils import timezone

from api import conteo
from api.models import ConteoProcedencia, PasarelaCheckout

pytestmark = pytest.mark.django_db

URL = "/api/conteo/teaser/"


@pytest.fixture(autouse=True)
def _cache_limpia(django_cache_cleared):
    """El techo por IP vive en la caché: sin limpiarla, los tests se lo gastan entre sí."""


def _hoy():
    return timezone.now().date()


def _filas(tipo):
    return {f.valor: f.cantidad for f in ConteoProcedencia.objects.filter(fecha=_hoy(), tipo=tipo)}


# --- Compras de prueba ---------------------------------------------------------


def _compra(checkout_id, **campos):
    return PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.MERCADOPAGO, checkout_id=checkout_id, codigo_producto="informe_natal",
        acreditado_at=timezone.now() - datetime.timedelta(hours=2), **campos,
    )


def test_una_compra_con_mail_de_prueba_no_es_una_venta(settings):
    settings.MAILS_DE_PRUEBA = ["yo@ejemplo.com"]
    _compra("mp_prueba", mail_comprador="Yo@Ejemplo.com")
    _compra("mp_real", mail_comprador="cliente@ejemplo.com")

    assert conteo._compras_pagas().count() == 1
    assert conteo._compras_pagas().get().checkout_id == "mp_real"


def test_una_compra_de_una_cuenta_de_prueba_tampoco_cuenta(settings, make_account):
    settings.MAILS_DE_PRUEBA = ["yo@ejemplo.com"]
    mia = make_account(email="yo@ejemplo.com")
    _compra("mp_de_mi_cuenta", account=mia)

    assert conteo._compras_pagas().count() == 0


def test_una_entrada_con_asterisco_compara_por_prefijo(settings, make_account):
    settings.MAILS_DE_PRUEBA = ["yo*", "otro@ejemplo.com"]
    _compra("mp_pago_yo", mail_comprador="Yo+prueba@ejemplo.com")
    _compra("mp_cuenta_yo", account=make_account(email="yo@otro-dominio.com"))
    _compra("mp_exacto", mail_comprador="otro@ejemplo.com")
    _compra("mp_real", mail_comprador="cliente@ejemplo.com")
    # El prefijo es del inicio del mail, no de cualquier parte.
    _compra("mp_contiene", mail_comprador="soy.yo@ejemplo.com")

    assert set(conteo._compras_pagas().values_list("checkout_id", flat=True)) == {"mp_real", "mp_contiene"}


def test_un_asterisco_solo_no_borra_todas_las_ventas(settings):
    settings.MAILS_DE_PRUEBA = ["*"]
    _compra("mp_1", mail_comprador="a@ejemplo.com")

    assert conteo._compras_pagas().count() == 1


def test_sin_lista_de_prueba_todas_cuentan(settings):
    settings.MAILS_DE_PRUEBA = []
    _compra("mp_1", mail_comprador="a@ejemplo.com")
    _compra("mp_2")

    assert conteo._compras_pagas().count() == 2


def test_el_tablero_y_el_resumen_no_suman_las_pruebas(settings):
    settings.MAILS_DE_PRUEBA = ["yo@ejemplo.com"]
    _compra("mp_prueba", mail_comprador="yo@ejemplo.com")

    assert sum(conteo.tablero()["eventos"]["compra_pagada"]) == 0
    assert conteo.resumen(dias=7)["total"]["compra_pagada"] == 0


# --- La fuente de una campaña propia --------------------------------------------


def _visita(utm, gclid=False):
    conteo.contar_visita("nueva", {"utm_source": utm, "gclid": gclid, "referrer": ""}, "AR")


def test_una_campana_propia_guarda_el_nombre_de_su_fuente():
    _visita("ChatGPT.com")
    _visita("chatgpt.com")

    assert _filas("utm") == {"chatgpt.com": 2}


def test_google_ads_y_el_trafico_sin_utm_no_ensucian_las_fuentes():
    _visita("google")
    _visita("", gclid=True)
    _visita("")

    assert _filas("utm") == {}


def test_una_fuente_con_caracteres_raros_se_guarda_como_otra():
    _visita("<script>alert(1)</script>")
    _visita("con espacios")

    assert _filas("utm") == {"otra": 2}


def test_las_fuentes_distintas_por_dia_tienen_techo():
    for i in range(conteo.MAX_FUENTES_POR_DIA + 5):
        _visita(f"fuente{i}")

    filas = _filas("utm")
    assert len(filas) == conteo.MAX_FUENTES_POR_DIA + 1
    assert filas["otras"] == 5
    # Una fuente que ya estaba sigue sumando aunque se haya llegado al techo.
    _visita("fuente0")
    assert _filas("utm")["fuente0"] == 2


def test_calcular_una_carta_tambien_guarda_la_fuente():
    conteo.contar_procedencia({"utm_source": "perplexity", "gclid": False, "referrer": ""}, "AR")

    assert _filas("utm") == {"perplexity": 1}


# --- Los pasos del teaser por canal y por moneda --------------------------------


def _mandar(client, **cuerpo):
    return client.post(URL, data=cuerpo, content_type="application/json")


def test_un_paso_se_cuenta_por_canal_y_por_moneda(client):
    r = _mandar(
        client, evento="cierre_visto", moneda="ars",
        procedencia={"utm_source": "", "gclid": True, "referrer": "", "zona": "America/Argentina/Buenos_Aires"},
    )

    assert r.status_code == 204
    assert _filas("teaser_canal") == {"cierre_visto:google_ads": 1}
    assert _filas("teaser_moneda") == {"cierre_visto:ars": 1}


def test_cada_paso_cuenta_por_separado(client):
    procedencia = {"utm_source": "", "gclid": False, "referrer": ""}
    _mandar(client, evento="cierre_visto", moneda="usd", procedencia=procedencia)
    _mandar(client, evento="clic_cierre", moneda="usd", procedencia=procedencia)
    _mandar(client, evento="clic_cierre", moneda="usd", procedencia=procedencia)

    assert _filas("teaser_canal") == {"cierre_visto:directo": 1, "clic_cierre:directo": 2}


def test_sin_procedencia_o_sin_moneda_el_paso_cuenta_igual_y_no_inventa(client):
    r = _mandar(client, evento="datos_abiertos")

    assert r.status_code == 204
    assert _filas("teaser_canal") == {}
    assert _filas("teaser_moneda") == {}


def test_una_moneda_o_procedencia_invalida_no_cuenta_nada(client):
    r = _mandar(client, evento="cierre_visto", moneda="doblones", procedencia={"gclid": True})

    assert r.status_code == 400
    assert _filas("teaser_canal") == {}
