"""`order.refunded` revoca el derecho y anota la deuda.

Política decidida el 02-09-2026: **no se le quita a nadie un informe ya
entregado**. Se devuelve la plata, el derecho baja lo que se pueda, y lo que no
alcanza a cubrirse queda como deuda de la cuenta — que se cancela contra la
próxima compra, y a la tercera deja la cuenta `flagged` para revisión.

El plan viejo decía lo contrario (revocar el acceso, 404 en el GET y en el PDF).
Se descartó: el texto que alguien ya leyó no se puede "desleer", y sacárselo
después de devolverle la plata es pelearse con un cliente que ya se fue.
"""

import json

import pytest

from api.canje import canjear, otorgar
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
        "id": "ord_1", "checkout_id": "chk_1", "product_id": "prod_uno",
        "subtotal_amount": 2900, "currency": "usd", "status": "refunded",
    }
    orden.update(cambios)
    return orden


def _entregar(client, orden=None, tipo="order.refunded", webhook_id="msg_1"):
    body = json.dumps({"type": tipo, "data": orden or _orden()}).encode()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json",
        **_firmar(body, webhook_id=webhook_id),
    )


def _restante(cuenta, codigo="informe_natal") -> int:
    d = Derecho.objects.filter(account=cuenta, codigo_producto=codigo).first()
    return d.cantidad_restante if d else 0


@pytest.fixture
def compro(make_account):
    """Una cuenta que pagó un informe suelto y todavía no lo usó."""
    cuenta = make_account()
    PolarCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
    )
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:order:ord_1")
    return cuenta


def test_el_reembolso_baja_el_derecho_no_usado(client, compro):
    _entregar(client)

    compro.refresh_from_db()
    assert _restante(compro) == 0
    assert compro.deuda == 0


def test_lo_ya_leido_queda_como_deuda_y_no_se_le_quita_a_nadie(client, compro, make_chart):
    canjear(compro, "leer_informe", make_chart(account=compro))

    _entregar(client)

    compro.refresh_from_db()
    assert compro.deuda == 1
    # El consumo que dejó la lectura sigue ahí: el texto entregado no se toca.
    assert Movimiento.objects.filter(tipo="consumo").count() == 1


def test_reembolsar_un_pack_descuenta_sus_cinco_unidades(client, make_account):
    """`revocar` traduce por el multiplicador del catálogo: una unidad
    reembolsada del pack son cinco informes, no uno."""
    cuenta = make_account()
    PolarCheckout.objects.create(
        checkout_id="chk_5", account=cuenta, codigo_producto="pack_5_natal",
    )
    otorgar(cuenta, "pack_5_natal", 1, origen="compra", external_id="polar:order:ord_5")

    _entregar(client, orden=_orden(id="ord_5", checkout_id="chk_5",
                                   product_id="prod_cinco", subtotal_amount=12500))

    assert _restante(cuenta) == 0


def test_el_mismo_reembolso_dos_veces_no_descuenta_dos(client, compro):
    """Polar reintenta: la clave es el id de la orden, con su propio prefijo
    para no chocar con el otorgamiento de esa misma orden."""
    _entregar(client, webhook_id="msg_1")
    _entregar(client, webhook_id="msg_2")

    assert Movimiento.objects.filter(tipo="revocacion").count() == 1


def test_el_reembolso_no_choca_con_el_otorgamiento_de_la_misma_orden(client, compro):
    """`polar:order:ord_1` y `polar:refund:ord_1` comparten el id de orden pero
    no el prefijo: si fueran la misma clave, el reembolso se descartaría como
    duplicado del pago y no revocaría nada."""
    _entregar(client)

    assert Movimiento.objects.filter(external_id="polar:order:ord_1").exists()
    assert Movimiento.objects.filter(external_id="polar:refund:ord_1").exists()


def test_un_reembolso_de_una_cuenta_ya_borrada_no_explota(client, make_account):
    """RF22: el chargeback puede llegar meses después del borrado. `revocar`
    tolera `account=None` y registra el movimiento igual, para que la
    contabilidad cierre."""
    cuenta = make_account()
    fila = PolarCheckout.objects.create(
        checkout_id="chk_1", account=cuenta, codigo_producto="informe_natal",
    )
    cuenta.delete()
    fila.refresh_from_db()

    resp = _entregar(client)

    assert 200 <= resp.status_code < 300


def test_un_producto_que_no_mapeamos_no_revoca(client, compro):
    resp = _entregar(client, orden=_orden(product_id="prod_desconocido"))

    assert 200 <= resp.status_code < 300
    assert _restante(compro) == 1
