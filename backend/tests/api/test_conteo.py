"""Conteo propio, sin cookies: cuántas cartas se calculan y cuántos pagos se abren por día.

PostHog sólo ve a quien acepta las cookies (el 10..16-10-2026: 135 personas
contra 481 clics de Google Ads). Estos números son el total real, sin datos
personales: una fila por día y evento con un contador."""

import datetime

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from api import conteo
from api.models import ConteoDiario, PasarelaCheckout

pytestmark = pytest.mark.django_db

PREVIEW = "/api/charts/preview/"
DATOS = {"date": "1990-05-10", "time": "14:30", "lat": -34.6, "lng": -58.4}


def _hoy():
    return timezone.now().date()


def test_contar_suma_de_a_uno_por_dia_y_evento():
    conteo.contar("carta_calculada")
    conteo.contar("carta_calculada")
    conteo.contar("checkout_abierto")
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="carta_calculada").cantidad == 2
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="checkout_abierto").cantidad == 1


def test_un_evento_desconocido_no_se_cuenta(caplog):
    conteo.contar("cualquiera")
    assert not ConteoDiario.objects.exists()
    assert "cualquiera" in caplog.text


def test_si_la_base_falla_no_rompe_a_quien_cuenta_ni_su_transaccion(monkeypatch, caplog):
    def explota(*a, **k):
        raise DatabaseError("caída")

    monkeypatch.setattr(ConteoDiario.objects, "get_or_create", explota)
    with transaction.atomic():
        conteo.contar("carta_calculada")
        # La transacción de afuera sigue usable: el fallo quedó en su savepoint.
        assert ConteoDiario.objects.count() == 0
    assert "conteo" in caplog.text


def test_la_vista_previa_cuenta_una_carta_calculada(client):
    assert client.post(PREVIEW, DATOS, content_type="application/json").status_code == 200
    assert ConteoDiario.objects.get(fecha=_hoy(), evento="carta_calculada").cantidad == 1


def test_una_vista_previa_rechazada_no_cuenta(client):
    r = client.post(PREVIEW, {"date": "no"}, content_type="application/json")
    assert r.status_code == 400
    assert not ConteoDiario.objects.exists()


def test_el_resumen_suma_siete_dias_completos_y_hoy_aparte():
    # El mail sale a las 10 UTC: hoy tiene unas horas y no puede leerse como un
    # día entero junto a los otros.
    ayer = _hoy() - datetime.timedelta(days=1)
    hace_7 = _hoy() - datetime.timedelta(days=7)
    hace_8 = _hoy() - datetime.timedelta(days=8)
    ConteoDiario.objects.create(fecha=_hoy(), evento="carta_calculada", cantidad=7)
    ConteoDiario.objects.create(fecha=ayer, evento="carta_calculada", cantidad=3)
    ConteoDiario.objects.create(fecha=hace_7, evento="carta_calculada", cantidad=2)
    ConteoDiario.objects.create(fecha=hace_8, evento="carta_calculada", cantidad=100)
    ConteoDiario.objects.create(fecha=ayer, evento="checkout_abierto", cantidad=1)
    ayer_dt = timezone.now() - datetime.timedelta(days=1)
    PasarelaCheckout.objects.create(checkout_id="cs_1", codigo_producto="informe_natal", acreditado_at=ayer_dt)
    # Un canje con cupón del 100 % no es una compra paga, ni una reembolsada.
    PasarelaCheckout.objects.create(checkout_id="cupon_x", codigo_producto="informe_natal", acreditado_at=ayer_dt)
    PasarelaCheckout.objects.create(
        checkout_id="cs_3", codigo_producto="informe_natal", acreditado_at=ayer_dt, reembolsado_centavos=500,
    )
    PasarelaCheckout.objects.create(checkout_id="cs_2", codigo_producto="informe_natal")

    r = conteo.resumen(dias=7)

    assert r["total"] == {"carta_calculada": 5, "checkout_abierto": 1, "compra_pagada": 1}
    assert r["hoy"] == {"carta_calculada": 7, "checkout_abierto": 0, "compra_pagada": 0}
    assert str(_hoy()) not in r["por_dia"] and str(hace_8) not in r["por_dia"]
    assert r["por_dia"][str(ayer)] == {"carta_calculada": 3, "checkout_abierto": 1, "compra_pagada": 1}


def test_crear_una_carta_con_cuenta_tambien_cuenta(account_client):
    assert account_client.post("/api/charts/", DATOS, format="json").status_code == 201
    assert ConteoDiario.objects.get(evento="carta_calculada").cantidad == 1


def test_si_el_adelanto_falla_la_carta_no_se_cuenta(client, monkeypatch):
    from api import views

    def rompe(_):
        raise RuntimeError("teaser roto")

    monkeypatch.setattr(views, "teaser", rompe)
    client.raise_request_exception = False
    assert client.post(PREVIEW, DATOS, content_type="application/json").status_code == 500
    assert not ConteoDiario.objects.exists()


def test_abrir_cualquier_checkout_de_stripe_lo_cuenta(settings, monkeypatch):
    # Se cuenta donde pasan todos (la llamada a Stripe), no en cada vista: un
    # camino de pago nuevo no puede olvidarse de contar.
    from api import stripe_client

    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"

    class _Sesion:
        id, url = "cs_test_1", "https://checkout.stripe.com/c/pay/cs_test_1"

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **k: _Sesion()))
    stripe_client.crear_checkout(None, "informe_natal", locale="es", terminos=True)
    assert ConteoDiario.objects.get(evento="checkout_abierto").cantidad == 1


def test_la_serie_va_del_dia_mas_viejo_a_hoy_con_ceros_donde_no_hubo_nada():
    ayer = _hoy() - datetime.timedelta(days=1)
    ConteoDiario.objects.create(fecha=_hoy(), evento="carta_calculada", cantidad=4)
    ConteoDiario.objects.create(fecha=ayer, evento="checkout_abierto", cantidad=2)
    PasarelaCheckout.objects.create(checkout_id="cs_1", codigo_producto="informe_natal", acreditado_at=timezone.now())

    s = conteo.serie(dias=3)

    assert s["fechas"] == [str(_hoy() - datetime.timedelta(days=2)), str(ayer), str(_hoy())]
    assert s["carta_calculada"] == [0, 0, 4]
    assert s["checkout_abierto"] == [0, 2, 0]
    assert s["compra_pagada"] == [0, 0, 1]


def test_el_grafico_es_un_svg_con_una_linea_por_serie():
    from api.grafico_conteo import svg_lineas

    svg = svg_lineas({
        "fechas": ["2026-10-16", "2026-10-17"],
        "carta_calculada": [3, 9], "checkout_abierto": [0, 1], "compra_pagada": [0, 0],
    })
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert svg.count("<polyline") == 3
    assert "Cartas calculadas" in svg and "Pagos abiertos" in svg and "Compras pagas" in svg
    # El máximo del eje sale del dato: 9.
    assert ">9<" in svg


def test_sin_datos_el_grafico_no_divide_por_cero():
    from api.grafico_conteo import svg_lineas

    svg = svg_lineas({"fechas": ["2026-10-17"], "carta_calculada": [0], "checkout_abierto": [0], "compra_pagada": [0]})
    assert svg.startswith("<svg")


def test_cada_grafico_escala_a_sus_propias_series():
    from api.grafico_conteo import svg_lineas

    datos = {"fechas": ["2026-10-16", "2026-10-17"],
             "carta_calculada": [30, 90], "checkout_abierto": [1, 3], "compra_pagada": [0, 1]}
    pagos = svg_lineas(datos, ("checkout_abierto", "compra_pagada"))
    assert pagos.count("<polyline") == 2 and ">3<" in pagos and ">90<" not in pagos
