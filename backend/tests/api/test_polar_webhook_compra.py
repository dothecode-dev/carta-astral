"""`order.paid` otorga lo que se compró.

Esta capa es pegamento y nada más: resolver a quién y qué, y llamar a
`canje.aplicar_compra`, que ya valida el monto contra el catálogo, es
idempotente por `external_id` y canjea en el acto si el producto da una sola
unidad. Duplicar acá cualquiera de esas tres cosas sería tener dos fuentes de
verdad sobre la misma plata.

La forma del payload ya no es una suposición: el 02-09-2026 llegó un pago real
y la fijó `test_polar_orden_real.py`, con los campos copiados de esa entrega.
De ahí salió que el monto contra el que se valida es `subtotal_amount` —el
precio de lista— y no `net_amount`, que viene descontado de impuestos.
"""

import json

import pytest

from api.models import Derecho, Movimiento, PolarCheckout
from tests.api.polar_firma import SECRETO, firmar as _firmar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {
        "prod_uno": "informe_natal",
        "prod_cinco": "pack_5_natal",
    }


def _orden(**cambios) -> dict:
    orden = {
        "id": "ord_1",
        "checkout_id": "chk_1",
        "product_id": "prod_uno",
        "subtotal_amount": 2900,
        "currency": "usd",
        "status": "paid",
    }
    orden.update(cambios)
    return orden


def _entregar(client, tipo="order.paid", orden=None, webhook_id="msg_1"):
    body = json.dumps({"type": tipo, "data": orden or _orden()}).encode()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json",
        **_firmar(body, webhook_id=webhook_id),
    )


def _restante(cuenta, codigo="informe_natal") -> int:
    d = Derecho.objects.filter(account=cuenta, codigo_producto=codigo).first()
    return d.cantidad_restante if d else 0


@pytest.fixture
def checkout(make_account):
    cuenta = make_account()
    PolarCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
    )
    return cuenta


def test_order_paid_otorga_el_derecho(client, checkout):
    _entregar(client)

    assert _restante(checkout) == 1


def test_el_pack_otorga_sus_cinco_unidades(client, make_account):
    cuenta = make_account()
    PolarCheckout.objects.create(
        checkout_id="chk_5", account=cuenta, codigo_producto="pack_5_natal",
    )

    _entregar(client, orden=_orden(checkout_id="chk_5", product_id="prod_cinco", subtotal_amount=12500))

    assert _restante(cuenta) == 5


def test_la_misma_orden_dos_veces_otorga_una_sola(client, checkout):
    """Polar reintenta hasta diez veces y cada reintento trae otro
    `webhook-id`. Por eso la clave de idempotencia es el id de la ORDEN, no el
    del evento."""
    _entregar(client, webhook_id="msg_1")
    _entregar(client, webhook_id="msg_2")

    assert _restante(checkout) == 1
    assert Movimiento.objects.filter(tipo="otorgamiento").count() == 1


def test_order_created_no_otorga_nada(client, checkout):
    """Llega con la orden en pending: la plata no está confirmada."""
    _entregar(client, tipo="order.created")

    assert _restante(checkout) == 0


def test_un_monto_que_no_es_el_del_catalogo_no_otorga(client, checkout):
    """Hay dos fuentes de precio —nuestro catálogo y el de Polar— y si divergen
    no se acredita. `aplicar_compra` lo rechaza y lo loguea: caja cerrada en
    silencio es peor que caja cerrada con un error a la vista."""
    resp = _entregar(client, orden=_orden(subtotal_amount=100))

    assert 200 <= resp.status_code < 300
    assert _restante(checkout) == 0


def test_un_producto_que_no_mapeamos_no_otorga(client, checkout):
    """Una orden de un producto que no está en POLAR_PRODUCTOS se descarta:
    acreditar "algo" ante un producto desconocido es peor que no acreditar."""
    resp = _entregar(client, orden=_orden(product_id="prod_que_no_conocemos"))

    assert 200 <= resp.status_code < 300
    assert _restante(checkout) == 0


def test_un_checkout_desconocido_responde_2xx_y_no_otorga(client):
    """No sabemos a quién acreditarle. 2xx a propósito: un 4xx acá suma a las
    diez entregas fallidas que deshabilitan el endpoint para todos."""
    resp = _entregar(client, orden=_orden(checkout_id="chk_que_no_existe"))

    assert 200 <= resp.status_code < 300
    assert Movimiento.objects.count() == 0


def test_con_carta_atada_el_informe_arranca_solo(client, make_account, make_chart):
    """Pagar y que el informe ya se esté escribiendo es el flujo que se vende:
    `aplicar_compra` canjea en el acto cuando el producto da una sola unidad."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PolarCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal", chart=carta,
    )

    _entregar(client)

    assert Movimiento.objects.filter(tipo="consumo", chart=carta).exists()


def test_la_cuenta_se_resuelve_por_metadata_si_no_hay_checkout(client, make_account):
    """Respaldo: la propagación de metadata del checkout a la orden no está en
    el contrato publicado de Polar, pero si viene, sirve para no perder un pago
    cuya fila de checkout falte."""
    cuenta = make_account()

    _entregar(client, orden=_orden(checkout_id="chk_sin_fila",
                                   metadata={"account_id": str(cuenta.pk)}))

    assert _restante(cuenta) == 1
