"""`POST /api/checkout/` abre la sesión de pago en Stripe: tests 26-30.

Del navegador viene QUÉ producto se compra y, opcionalmente, sobre qué carta.
El precio no: lo pone el catálogo al abrir la sesión, y el webhook lo vuelve a
validar contra lo que Stripe cobró antes de otorgar nada.
"""

import pytest

from api import mantenimiento, stripe_client
from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db

URL = "/api/checkout/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    settings.STRIPE_SUCCESS_URL = (
        "https://astraguia.com/{locale}/compra?session_id={CHECKOUT_SESSION_ID}"
    )


@pytest.fixture
def stripe_responde(monkeypatch):
    """Captura los parámetros con los que se crea la sesión, sin salir a la red."""
    pedidos = []

    class _Sesion:
        id = "cs_test_nueva"
        url = "https://checkout.stripe.com/c/pay/cs_test_nueva"

    def crear(**params):
        pedidos.append(params)
        return _Sesion()

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(crear))
    return pedidos


def test_sin_sesion_no_se_puede_comprar(client):
    assert client.post(URL, {"producto": "informe_natal"}).status_code == 401


def test_devuelve_la_url_y_guarda_a_quien_compra(account_client, stripe_responde):
    datos = account_client.post(URL, {"producto": "informe_natal"}).json()

    assert datos["url"] == "https://checkout.stripe.com/c/pay/cs_test_nueva"
    guardado = PasarelaCheckout.objects.get(checkout_id="cs_test_nueva")
    assert guardado.account_id == account_client.account.pk
    assert guardado.codigo_producto == "informe_natal"


def test_el_cliente_no_elige_el_precio(account_client, stripe_responde):
    """El precio lo pone el catálogo: del navegador sólo viene el producto."""
    account_client.post(URL, {"producto": "informe_natal", "amount": 1})

    enviado = stripe_responde[0]
    assert enviado["line_items"] == [{"price": "price_natal", "quantity": 1}]
    assert "amount" not in enviado


def test_la_carta_queda_atada_a_la_compra(account_client, stripe_responde, make_chart):
    carta = make_chart(account=account_client.account)

    account_client.post(URL, {"producto": "informe_natal", "chart_id": str(carta.uuid)})

    assert PasarelaCheckout.objects.get(checkout_id="cs_test_nueva").chart_id == carta.pk


def test_una_carta_ajena_no_se_puede_atar(
    account_client, stripe_responde, make_chart, make_account,
):
    """Si no, se compra un informe y se lo entrega en la carta de otro."""
    ajena = make_chart(account=make_account())

    resp = account_client.post(URL, {"producto": "informe_natal", "chart_id": str(ajena.uuid)})

    assert resp.status_code == 404
    assert PasarelaCheckout.objects.count() == 0


def test_un_producto_que_no_existe_es_400(account_client, stripe_responde):
    assert account_client.post(URL, {"producto": "pack_100"}).status_code == 400
    assert not stripe_responde


def test_un_producto_gratis_no_se_cobra(account_client, stripe_responde):
    assert account_client.post(URL, {"producto": "lectura_breve"}).status_code == 400
    assert not stripe_responde


def test_sin_credenciales_el_cobro_no_esta_disponible(account_client, settings, stripe_responde):
    settings.STRIPE_SECRET_KEY = ""

    assert account_client.post(URL, {"producto": "informe_natal"}).status_code == 503
    assert not stripe_responde


def test_un_producto_sin_precio_en_stripe_no_abre_la_sesion(
    account_client, settings, stripe_responde,
):
    """El catálogo y Stripe son dos listas que hay que mantener alineadas:
    mejor fallar acá que abrir un pago que después nadie puede acreditar."""
    settings.STRIPE_PRECIOS = {"price_pack": "pack_5_natal"}

    assert account_client.post(URL, {"producto": "informe_natal"}).status_code == 503
    assert not stripe_responde


def test_en_mantenimiento_no_se_abre_ninguna_sesion(account_client, stripe_responde, db_cache):
    """Cobrar y no poder entregar es la peor combinación posible."""
    mantenimiento.activar()
    try:
        resp = account_client.post(URL, {"producto": "informe_natal"})
    finally:
        mantenimiento.desactivar()

    assert resp.status_code == 503
    assert not stripe_responde
    assert PasarelaCheckout.objects.count() == 0


def test_el_idioma_viaja_a_stripe_y_a_la_url_de_vuelta(account_client, stripe_responde):
    account_client.post(URL, {"producto": "informe_natal", "locale": "pt"})

    enviado = stripe_responde[0]
    assert enviado["locale"] == "pt"
    assert enviado["success_url"].startswith("https://astraguia.com/pt/compra")
    assert PasarelaCheckout.objects.get(checkout_id="cs_test_nueva").locale == "pt"


def test_un_idioma_inventado_cae_en_es_y_no_viaja(account_client, stripe_responde):
    """El locale llega del navegador y termina en una URL: lista blanca."""
    account_client.post(URL, {"producto": "informe_natal", "locale": "../evil.com"})

    enviado = stripe_responde[0]
    assert enviado["locale"] == "es"
    assert "evil.com" not in enviado["success_url"]
    assert enviado["success_url"].startswith("https://astraguia.com/es/compra")


def test_la_sesion_lleva_el_id_de_la_cuenta_como_respaldo(account_client, stripe_responde):
    """La fila propia manda, pero si se perdiera, la metadata resuelve."""
    account_client.post(URL, {"producto": "informe_natal"})

    assert stripe_responde[0]["metadata"]["account_id"] == str(account_client.account.pk)
