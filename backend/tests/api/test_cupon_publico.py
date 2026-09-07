"""`GET /api/cupones/<codigo>/?producto=`: para pintar el precio tachado en
`/precios` antes de que haya cuenta. Sólo para pintar: la validación que vale
es la del checkout.

Devuelve el catálogo con la misma forma que `GET /api/catalogo/`, filtrado a
lo que el cupón abarca y con el precio final; nunca la descripción interna,
los usos restantes ni los ids de Stripe. Con throttle por IP: es la puerta
por la que se enumeraría el diccionario de códigos.
"""
import pytest
from django.core.cache import cache

from api.cupones import precio_final
from api.models import Cupon

pytestmark = pytest.mark.django_db


@pytest.fixture
def promo():
    return Cupon.objects.create(codigo="PROMO30", porcentaje=30, productos=["informe_natal", "pack_5_natal"],
                                usos_maximos=10, descripcion="secreto interno",
                                stripe_coupon_id="cup_1", stripe_promotion_code_id="promo_1")


def test_el_endpoint_no_pide_sesion(client, promo):
    assert client.get("/api/cupones/PROMO30/").status_code == 200


def test_un_cupon_valido_devuelve_los_precios_ya_descontados(client, promo):
    r = client.get("/api/cupones/promo30/").json()

    assert r["valido"] is True and r["codigo"] == "PROMO30" and r["porcentaje"] == 30
    final, descuento = precio_final(2900, 30)
    natal = next(p for p in r["productos"] if p["codigo"] == "informe_natal")
    assert natal["precio_centavos"] == 2900
    assert natal["precio_final_centavos"] == final and natal["descuento_centavos"] == descuento
    assert natal["moneda"] == "usd" and natal["otorga"] == [{"codigo": "informe_natal", "cantidad": 1}]


def test_solo_lista_los_productos_que_el_cupon_abarca(client, promo):
    codigos = [p["codigo"] for p in client.get("/api/cupones/PROMO30/").json()["productos"]]
    assert codigos == ["informe_natal", "pack_5_natal"]


def test_no_revela_nada_interno(client, promo):
    cuerpo = client.get("/api/cupones/PROMO30/").content.decode()
    for secreto in ("secreto interno", "cup_1", "promo_1", "usos"):
        assert secreto not in cuerpo


def test_un_codigo_invalido_no_dice_si_existe(client, promo):
    Cupon.objects.create(codigo="APAGADO", porcentaje=10, productos=["informe_natal"], usos_maximos=1, activo=False)

    inexistente = client.get("/api/cupones/NADA/").json()
    apagado = client.get("/api/cupones/APAGADO/").json()

    assert inexistente == apagado == {"valido": False, "motivo": "invalido"}


def test_un_cupon_agotado_lo_dice(client, promo):
    from api.models import CuponUso

    promo.usos_maximos = 1
    promo.save()
    CuponUso.objects.create(cupon=promo, codigo_producto="informe_natal", descuento_centavos=870,
                            monto_pagado_centavos=2030, external_id="stripe:session:x")

    assert client.get("/api/cupones/PROMO30/").json() == {"valido": False, "motivo": "agotado"}


def test_con_producto_dice_si_aplica_a_ese(client, promo):
    assert client.get("/api/cupones/PROMO30/", {"producto": "pack_3_natal"}).json() == {"valido": False, "motivo": "no_aplica"}
    assert client.get("/api/cupones/PROMO30/", {"producto": "informe_natal"}).json()["valido"] is True


def test_un_codigo_con_caracteres_raros_es_invalido_sin_500(client):
    assert client.get("/api/cupones/%C3%B1o%20va/").json() == {"valido": False, "motivo": "invalido"}


def test_el_throttle_frena_la_enumeracion(client, monkeypatch, promo):
    monkeypatch.setattr("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", {"cupon": "2/hour"})
    cache.clear()

    assert client.get("/api/cupones/A/").status_code == 200
    assert client.get("/api/cupones/B/").status_code == 200
    assert client.get("/api/cupones/C/").status_code == 429


def test_el_checkout_tambien_tiene_techo(account_client, monkeypatch):
    monkeypatch.setattr("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", {"checkout": "1/hour"})
    cache.clear()

    account_client.post("/api/checkout/", {"producto": "informe_natal"})
    assert account_client.post("/api/checkout/", {"producto": "informe_natal"}).status_code == 429
