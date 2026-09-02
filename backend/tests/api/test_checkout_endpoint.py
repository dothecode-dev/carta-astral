"""`POST /api/checkout/`: abre el pago y ata la orden a quien la pidió.

Polar devuelve el id del checkout y, más tarde, la orden lo trae en
`order.checkout_id`. Esa relación se guarda de este lado porque la propagación
de `metadata` del checkout a la orden **no está en el contrato publicado** de
Polar: `checkout_id` sí está garantizado. Sin la tabla, un pago que llega sin
metadata no sabe a qué cuenta acreditarle nada.
"""

import json

import httpx
import pytest

from api import polar
from api.models import PolarCheckout

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_ACCESS_TOKEN = "polar_at_de_prueba"
    settings.POLAR_ENVIRONMENT = "sandbox"
    settings.POLAR_SUCCESS_URL = "https://astraguia.com/es/compra"
    settings.POLAR_PRODUCTOS = {
        "prod_uno": "informe_natal",
        "prod_tres": "pack_3_natal",
        "prod_cinco": "pack_5_natal",
    }


@pytest.fixture
def polar_responde(monkeypatch):
    pedidos = []

    def _armar(status=201, body=None):
        def handler(request: httpx.Request) -> httpx.Response:
            pedidos.append(request)
            return httpx.Response(
                status, json=body or {"id": "chk_1", "url": "https://polar.sh/pay/chk_1"}
            )

        monkeypatch.setattr(
            polar, "_client",
            lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=polar.TIMEOUT),
        )
        return pedidos

    return _armar


def test_sin_sesion_no_se_puede_comprar(client):
    assert client.post("/api/checkout/", {"producto": "informe_natal"}).status_code == 401


def test_devuelve_la_url_y_guarda_a_quien_compra(account_client, polar_responde):
    polar_responde()

    datos = account_client.post("/api/checkout/", {"producto": "informe_natal"}).json()

    assert datos["url"] == "https://polar.sh/pay/chk_1"
    guardado = PolarCheckout.objects.get(checkout_id="chk_1")
    assert guardado.account_id == account_client.account.pk
    assert guardado.codigo_producto == "informe_natal"


def test_el_cliente_no_elige_el_precio(account_client, polar_responde):
    """Del navegador viene QUÉ producto, nunca cuánto sale: el precio lo pone
    el catálogo y lo vuelve a validar el webhook contra la orden."""
    pedidos = polar_responde()

    account_client.post("/api/checkout/", {"producto": "informe_natal", "amount": 1})

    enviado = json.loads(pedidos[0].content)
    assert "amount" not in enviado
    assert enviado["products"] == ["prod_uno"]


def test_la_carta_queda_atada_a_la_compra(account_client, polar_responde, make_chart):
    """Comprar desde una carta tiene que terminar con esa carta escribiéndose,
    no con un derecho suelto que hay que ir a usar a mano."""
    polar_responde()
    carta = make_chart(account=account_client.account)

    account_client.post(
        "/api/checkout/", {"producto": "informe_natal", "chart_id": str(carta.uuid)}
    )

    assert PolarCheckout.objects.get(checkout_id="chk_1").chart_id == carta.pk


def test_una_carta_ajena_no_se_puede_atar(account_client, polar_responde, make_chart, make_account):
    """Si no, se compra un informe y se lo entrega en la carta de otro."""
    polar_responde()
    ajena = make_chart(account=make_account())

    resp = account_client.post(
        "/api/checkout/", {"producto": "informe_natal", "chart_id": str(ajena.uuid)}
    )

    assert resp.status_code == 404
    assert PolarCheckout.objects.count() == 0


def test_un_producto_que_no_existe_es_400(account_client):
    assert account_client.post("/api/checkout/", {"producto": "pack_100"}).status_code == 400


def test_un_producto_gratis_no_se_cobra(account_client):
    """`lectura_breve` vale 0: un checkout de US$ 0 deja una orden que el
    webhook no sabe validar."""
    assert account_client.post("/api/checkout/", {"producto": "lectura_breve"}).status_code == 400


def test_sin_producto_es_400(account_client):
    assert account_client.post("/api/checkout/", {}).status_code == 400


def test_si_polar_falla_no_deja_basura(account_client, polar_responde):
    """502 y ni una fila: un PolarCheckout huérfano haría que el webhook de
    otra orden pudiera resolver contra él."""
    polar_responde(status=500, body={"detail": "boom"})

    assert account_client.post("/api/checkout/", {"producto": "informe_natal"}).status_code == 502
    assert PolarCheckout.objects.count() == 0


def test_sin_token_configurado_es_503(account_client, settings):
    """Un problema de configuración nuestro no es culpa de quien compra: 503,
    no 400."""
    settings.POLAR_ACCESS_TOKEN = ""

    assert account_client.post("/api/checkout/", {"producto": "informe_natal"}).status_code == 503
