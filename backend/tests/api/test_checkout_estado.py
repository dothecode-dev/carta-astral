"""`GET /api/checkout/<checkout_id>/`: en qué quedó una compra, y a dónde ir.

Lo consulta la página de retorno, adonde Polar devuelve a quien pagó. Existe por
una carrera que no se puede evitar: el redirect del navegador es instantáneo y
el webhook que acredita puede llegar después. Sin este endpoint, la página
tendría que adivinar —y adivinar mal significa mostrarle el botón de comprar a
alguien que acaba de pagar—.

No dice nada que la cuenta no pueda ver: un checkout de otra persona responde
404, igual que una carta ajena.
"""

import json

import pytest

from api.models import PasarelaCheckout
from tests.api.polar_firma import SECRETO
from tests.api.polar_firma import firmar as _firmar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {"prod_uno": "informe_natal", "prod_cinco": "pack_5_natal"}


def _acreditar(client, checkout_id="chk_1", product_id="prod_uno", monto=2900):
    """Hace llegar el `order.paid` que acredita esa compra."""
    body = json.dumps({
        "type": "order.paid",
        "data": {
            "id": f"ord_{checkout_id}", "checkout_id": checkout_id,
            "product_id": product_id, "subtotal_amount": monto,
            "discount_amount": 0, "total_amount": monto,
        },
    }).encode()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json", **_firmar(body),
    )


def test_sin_sesion_no_se_puede_consultar(client):
    assert client.get("/api/checkout/chk_1/").status_code == 401


def test_un_checkout_de_otra_cuenta_es_404(account_client, make_account):
    """Mismo criterio que una carta ajena: para quien mira, no existe."""
    PasarelaCheckout.objects.create(
        checkout_id="chk_ajeno", account=make_account(), codigo_producto="informe_natal",
    )

    assert account_client.get("/api/checkout/chk_ajeno/").status_code == 404


def test_un_checkout_que_no_existe_es_404(account_client):
    assert account_client.get("/api/checkout/chk_inventado/").status_code == 404


def test_mientras_el_webhook_no_llega_la_compra_esta_pendiente(account_client, make_chart):
    """El caso de la carrera: la persona volvió antes que el webhook."""
    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    datos = account_client.get("/api/checkout/chk_1/").json()

    assert datos["estado"] == "pendiente"


def test_acreditada_y_con_carta_manda_a_la_carta(client, account_client, make_chart):
    """Comprar el informe desde una carta termina en esa carta, donde el
    informe ya se está escribiendo (lo arrancó el propio webhook)."""
    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    _acreditar(client)

    datos = account_client.get("/api/checkout/chk_1/").json()
    assert datos["estado"] == "acreditado"
    assert datos["destino"] == {"tipo": "carta", "id": str(carta.uuid)}


def test_un_pack_manda_a_la_cuenta(client, account_client, make_chart):
    """Cinco informes no son una carta: se usan cuando la persona quiera, así
    que el lugar donde eso se ve es su cuenta —aunque el pack se haya comprado
    mirando una carta—."""
    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="chk_5", account=account_client.account,
        codigo_producto="pack_5_natal", chart=carta,
    )

    _acreditar(client, checkout_id="chk_5", product_id="prod_cinco", monto=12500)

    datos = account_client.get("/api/checkout/chk_5/").json()
    assert datos["estado"] == "acreditado"
    assert datos["destino"] == {"tipo": "cuenta"}


def test_una_compra_suelta_sin_carta_manda_a_la_cuenta(client, account_client):
    PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account, codigo_producto="informe_natal",
    )

    _acreditar(client)

    datos = account_client.get("/api/checkout/chk_1/").json()
    assert datos["destino"] == {"tipo": "cuenta"}


def test_una_compra_cuya_carta_se_borro_manda_a_la_cuenta(client, account_client, make_chart):
    """`chart` es SET_NULL: la carta puede no estar cuando se pregunta.
    Mandar a `/carta/None` sería un 404 en la cara de quien pagó."""
    carta = make_chart(account=account_client.account)
    fila = PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    _acreditar(client)
    carta.delete()
    fila.refresh_from_db()

    datos = account_client.get("/api/checkout/chk_1/").json()
    assert datos["destino"] == {"tipo": "cuenta"}


def test_el_webhook_deja_marcada_la_compra_como_acreditada(client, account_client):
    """`acreditado_at` lo escribe el webhook y es lo que responde este endpoint.

    Se guarda en la fila y no se deduce mirando movimientos por fecha: dos
    compras del mismo producto en el mismo minuto no se distinguirían así.
    """
    fila = PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account, codigo_producto="informe_natal",
    )
    assert fila.acreditado_at is None

    _acreditar(client)

    fila.refresh_from_db()
    assert fila.acreditado_at is not None


def test_un_pago_rechazado_por_monto_no_marca_acreditado(client, account_client):
    """Si el monto no coincide con el catálogo no se otorga nada, y la página
    de retorno no puede decir que la compra está lista."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="chk_1", account=account_client.account, codigo_producto="informe_natal",
    )

    _acreditar(client, monto=100)

    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert account_client.get("/api/checkout/chk_1/").json()["estado"] == "pendiente"
