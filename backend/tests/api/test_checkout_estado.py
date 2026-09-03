"""`GET /api/checkout/<checkout_id>/`: en qué quedó una compra, y a dónde ir.

Lo consulta la página de retorno, adonde Stripe devuelve a quien pagó. Existe
por una carrera que no se puede evitar: el redirect del navegador es
instantáneo y el webhook que acredita puede llegar después. Sin este endpoint,
la página tendría que adivinar —y adivinar mal significa mostrarle el botón de
comprar a alguien que acaba de pagar—.

No dice nada que la cuenta no pueda ver: un checkout de otra persona responde
404, igual que una carta ajena.
"""

import json

import pytest

from api import webhooks_stripe
from api.models import PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}


@pytest.fixture
def acreditar(client, monkeypatch):
    """Hace llegar el `checkout.session.completed` que acredita esa compra."""
    def _acreditar(checkout_id="cs_1", price="price_natal", monto=2900):
        sesion = {
            "id": checkout_id, "payment_status": "paid",
            "amount_subtotal": monto, "amount_total": monto,
            "total_details": {"amount_tax": 0, "amount_discount": 0},
            "payment_intent": f"pi_{checkout_id}", "metadata": {},
            "line_items": {"data": [{"price": {"id": price}, "quantity": 1}]},
        }
        monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
        cuerpo = json.dumps({
            "id": "evt_1", "type": "checkout.session.completed",
            "data": {"object": {"id": checkout_id}},
        }).encode()
        return client.post(
            "/api/webhooks/stripe/", cuerpo, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
        )

    return _acreditar


def test_sin_sesion_no_se_puede_consultar(client):
    assert client.get("/api/checkout/cs_1/").status_code == 401


def test_un_checkout_de_otra_cuenta_es_404(account_client, make_account):
    """Mismo criterio que una carta ajena: para quien mira, no existe."""
    PasarelaCheckout.objects.create(
        checkout_id="cs_ajeno", account=make_account(), codigo_producto="informe_natal",
    )

    assert account_client.get("/api/checkout/cs_ajeno/").status_code == 404


def test_un_checkout_que_no_existe_es_404(account_client):
    assert account_client.get("/api/checkout/cs_inventado/").status_code == 404


def test_mientras_el_webhook_no_llega_la_compra_esta_pendiente(account_client, make_chart):
    """El caso de la carrera: la persona volvió antes que el webhook."""
    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    assert account_client.get("/api/checkout/cs_1/").json()["estado"] == "pendiente"


def test_acreditada_y_con_carta_manda_a_la_carta(account_client, make_chart, acreditar):
    """Comprar el informe desde una carta termina en esa carta, donde el
    informe ya se está escribiendo (lo arrancó el propio webhook)."""
    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    acreditar()

    datos = account_client.get("/api/checkout/cs_1/").json()
    assert datos["estado"] == "acreditado"
    assert datos["destino"] == {"tipo": "carta", "id": str(carta.uuid)}


def test_un_pack_manda_a_la_cuenta(account_client, make_chart, acreditar):
    """Cinco informes no son una carta: se usan cuando la persona quiera, así
    que el lugar donde eso se ve es su cuenta —aunque el pack se haya comprado
    mirando una carta—."""
    from api.catalogo import producto

    carta = make_chart(account=account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="cs_5", account=account_client.account,
        codigo_producto="pack_5_natal", chart=carta,
    )

    acreditar(checkout_id="cs_5", price="price_pack",
              monto=producto("pack_5_natal").precio_centavos)

    datos = account_client.get("/api/checkout/cs_5/").json()
    assert datos["estado"] == "acreditado"
    assert datos["destino"] == {"tipo": "cuenta"}


def test_una_compra_suelta_sin_carta_manda_a_la_cuenta(account_client, acreditar):
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account, codigo_producto="informe_natal",
    )

    acreditar()

    assert account_client.get("/api/checkout/cs_1/").json()["destino"] == {"tipo": "cuenta"}


def test_una_compra_cuya_carta_se_borro_manda_a_la_cuenta(
    account_client, make_chart, acreditar,
):
    """`chart` es SET_NULL: la carta puede no estar cuando se pregunta.
    Mandar a `/carta/None` sería un 404 en la cara de quien pagó."""
    carta = make_chart(account=account_client.account)
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account,
        codigo_producto="informe_natal", chart=carta,
    )

    acreditar()
    carta.delete()
    fila.refresh_from_db()

    assert account_client.get("/api/checkout/cs_1/").json()["destino"] == {"tipo": "cuenta"}


def test_el_webhook_deja_marcada_la_compra_como_acreditada(account_client, acreditar):
    """`acreditado_at` lo escribe el webhook y es lo que responde este endpoint.

    Se guarda en la fila y no se deduce mirando movimientos por fecha: dos
    compras del mismo producto en el mismo minuto no se distinguirían así.
    """
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account, codigo_producto="informe_natal",
    )
    assert fila.acreditado_at is None

    acreditar()

    fila.refresh_from_db()
    assert fila.acreditado_at is not None
    assert fila.payment_intent == "pi_cs_1"


def test_un_pago_rechazado_por_monto_no_marca_acreditado(account_client, acreditar):
    """Si el monto no coincide con el catálogo no se otorga nada, y la página
    de retorno no puede decir que la compra está lista."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account, codigo_producto="informe_natal",
    )

    acreditar(monto=100)

    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert account_client.get("/api/checkout/cs_1/").json()["estado"] == "pendiente"
