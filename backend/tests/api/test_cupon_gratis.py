"""El cupón del 100 %: el checkout resuelve solo, sin Stripe.

Es el único camino que entrega un producto de US$ 29 con un POST, así que
todo lo que el pago hace —acreditar, avisar, medir, arrancar el informe— lo
hace acá también, y todo lo que lo frena —mantenimiento, deuda, cuenta
marcada— lo frena acá también.
"""
import pytest

from api import analitica, mantenimiento, notificaciones, stripe_client
from api.models import Cupon, CuponUso, Derecho, Movimiento, PasarelaCheckout

pytestmark = pytest.mark.django_db

URL = "/api/checkout/"


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"

    def jamas(**p):
        raise AssertionError("el 100% no abre sesión en Stripe")

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(jamas))


@pytest.fixture
def regalo():
    return Cupon.objects.create(codigo="REGALO", porcentaje=100, productos=["informe_natal"], usos_maximos=1)


@pytest.fixture
def avisos(monkeypatch):
    llamadas = {"mail": [], "evento": [], "informe": []}
    monkeypatch.setattr(notificaciones, "notificar", lambda acc, ev, ctx, lang: llamadas["mail"].append((ev, ctx, lang)))
    monkeypatch.setattr(analitica, "evento", lambda acc, nombre, props: llamadas["evento"].append((nombre, props)))
    from api import compra_service
    monkeypatch.setattr(compra_service, "arrancar_informe", lambda cuenta, fila: llamadas["informe"].append(fila))
    return llamadas


def test_otorga_y_acredita_al_instante_sin_stripe(account_client, regalo, avisos):
    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "regalo", "locale": "pt"})

    assert r.status_code == 200, r.content
    url = r.json()["url"]
    assert url.startswith("/pt/compra?checkout_id=cupon_")
    fila = PasarelaCheckout.objects.get(checkout_id=url.split("checkout_id=")[1])
    assert fila.acreditado_at is not None
    assert fila.cupon == regalo and fila.descuento_centavos == 2900
    assert Derecho.objects.get(account=account_client.account, codigo_producto="informe_natal").cantidad_restante == 4
    mov = Movimiento.objects.get(external_id=f"cupon:{fila.checkout_id}")
    assert mov.origen == "cupon"
    uso = CuponUso.objects.get(cupon=regalo)
    assert (uso.account, uso.monto_pagado_centavos, uso.descuento_centavos) == (account_client.account, 0, 2900)
    assert uso.external_id == f"cupon:{fila.checkout_id}"


def test_la_pagina_de_retorno_lo_ve_acreditado(account_client, regalo, avisos):
    url = account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"}).json()["url"]
    checkout_id = url.split("checkout_id=")[1]

    r = account_client.get(f"/api/checkout/{checkout_id}/")

    assert r.status_code == 200
    assert r.json()["estado"] == "acreditado"


def test_avisa_mide_y_arranca_el_informe_como_un_pago(account_client, regalo, avisos, make_chart):
    carta = make_chart(account=account_client.account)

    account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO", "chart_id": str(carta.uuid), "locale": "en"})

    assert avisos["mail"] == [("compra_acreditada", {"producto": "informe_natal"}, "en")]
    (nombre, props), = avisos["evento"]
    assert nombre == "compra_completada"
    assert props["monto_centavos"] == 0 and props["cupon"] == "REGALO"
    (fila,) = avisos["informe"]
    assert fila.chart == carta


def test_dos_pedidos_seguidos_otorgan_una_sola_vez(account_client, regalo, avisos):
    account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})
    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})

    assert r.status_code == 400
    assert r.json()["motivo"] == "ya_usado"
    assert CuponUso.objects.count() == 1


def test_el_segundo_en_llegar_ve_agotado(account_client, make_account, regalo, avisos):
    from api.auth import create_session
    from rest_framework.test import APIClient

    otro = APIClient()
    otro.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(make_account())}")
    account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})

    r = otro.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})

    assert (r.status_code, r.json()["motivo"]) == (400, "agotado")


def test_en_mantenimiento_no_se_canjea(account_client, regalo, avisos, monkeypatch):
    monkeypatch.setattr(mantenimiento, "activo", lambda: True)
    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})
    assert r.status_code == 503
    assert CuponUso.objects.count() == 0


@pytest.mark.parametrize("campo", ["deuda", "flagged"])
def test_una_cuenta_con_deuda_o_marcada_no_canjea_un_regalo(account_client, regalo, avisos, campo):
    acc = account_client.account
    setattr(acc, campo, 1 if campo == "deuda" else True)
    acc.save()

    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"})

    assert (r.status_code, r.json()["motivo"]) == (400, "cuenta_no_habilitada")
    assert CuponUso.objects.count() == 0


def test_un_cupon_invalido_responde_400_con_motivo(account_client, avisos):
    r = account_client.post(URL, {"producto": "informe_natal", "cupon": "NOEXISTE"})
    assert (r.status_code, r.json()["motivo"]) == (400, "invalido")


def test_el_id_sintetico_no_parece_de_stripe(account_client, regalo, avisos):
    url = account_client.post(URL, {"producto": "informe_natal", "cupon": "REGALO"}).json()["url"]
    assert "checkout_id=cupon_" in url and "cs_" not in url
