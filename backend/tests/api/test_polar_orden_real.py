"""La forma de la orden, tomada de un pago real y no de lo que suponíamos.

El 02-09-2026 se pagó un informe de verdad en el sandbox (tarjeta de prueba) y
la entrega quedó guardada en el panel de Polar. Este archivo fija esa forma:
los campos de acá están copiados de ese payload, no escritos de memoria.

Lo que ese pago desmintió es el monto. Asumíamos que `net_amount` era el precio
del producto y es otra cosa: lo que le queda al vendedor una vez descontado el
impuesto que Polar recauda como merchant of record. Para un informe de US$ 29
comprado desde Argentina llegó `net_amount: 2397` con `tax_amount: 503`, y como
`aplicar_compra` compara el monto contra el catálogo, el pago se habría
rechazado por `MontoInvalido` aunque la firma hubiese estado bien.

El precio de lista es `subtotal_amount`: antes de impuestos y de descuentos, y
estable frente al país del comprador. Es lo que el catálogo representa y contra
lo que tiene sentido compararlo — la comprobación existe para detectar que el
precio en Polar y el nuestro se hayan desincronizado, no para auditar el IVA.
"""

import json

import pytest

from api.models import Derecho, Movimiento, PolarCheckout
from tests.api.polar_firma import SECRETO
from tests.api.polar_firma import firmar as _firmar

pytestmark = pytest.mark.django_db

# El id real del producto `informe_natal` en la organización de Polar.
PRODUCTO_INFORME = "e3e44b14-6d7b-4e29-b564-5c694559386c"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_WEBHOOK_SECRET = SECRETO
    settings.POLAR_PRODUCTOS = {PRODUCTO_INFORME: "informe_natal"}


def _orden_real(**cambios) -> dict:
    """La orden del pago del 02-09-2026, con los campos que mira el webhook.

    Los montos son los que llegaron: el precio es 2900 y `net_amount` 2397,
    que es la diferencia que rompía la acreditación.
    """
    orden = {
        "id": "fc50ffdc-b5b2-40ba-b1d3-bb2a55e8b641",
        "status": "paid",
        "paid": True,
        "subtotal_amount": 2900,
        "discount_amount": 0,
        "net_amount": 2397,
        "tax_amount": 503,
        "total_amount": 2900,
        "currency": "usd",
        "billing_reason": "purchase",
        "checkout_id": "c7487b81-903c-47bb-8f22-430e2ca75bda",
        "product_id": PRODUCTO_INFORME,
        "discount_id": None,
        "subscription_id": None,
        "metadata": {"chart_id": "9", "account_id": "6"},
    }
    orden.update(cambios)
    return orden


def _entregar(client, orden=None, tipo="order.paid"):
    body = json.dumps({"type": tipo, "data": orden or _orden_real()}).encode()
    return client.post(
        "/api/webhooks/polar/", body, content_type="application/json", **_firmar(body),
    )


@pytest.fixture
def checkout(make_account):
    cuenta = make_account()
    PolarCheckout.objects.create(
        checkout_id="c7487b81-903c-47bb-8f22-430e2ca75bda",
        account=cuenta,
        codigo_producto="informe_natal",
    )
    return cuenta


def _restante(cuenta, codigo="informe_natal") -> int:
    d = Derecho.objects.filter(account=cuenta, codigo_producto=codigo).first()
    return d.cantidad_restante if d else 0


def test_una_orden_real_acredita_el_informe(client, checkout):
    """El pago que quedó sin acreditar el 02-09-2026, tal como llegó."""
    _entregar(client)

    assert _restante(checkout) == 1


def test_el_impuesto_no_se_confunde_con_el_precio(client, checkout):
    """`net_amount` viene descontado de impuestos y NO es contra qué validar.

    Con una tasa distinta —otro país del comprador— el neto cambia y el precio
    de lista no: si el webhook volviera a mirar `net_amount`, este pago se
    rechazaría por monto inválido.
    """
    _entregar(client, orden=_orden_real(net_amount=1900, tax_amount=1000))

    assert _restante(checkout) == 1


def test_un_precio_de_lista_distinto_al_catalogo_no_acredita(client, checkout):
    """Lo que la comprobación existe para atajar: el producto en Polar quedó a
    otro precio que el catálogo. Ahí sí se frena todo y queda el error a la
    vista."""
    resp = _entregar(client, orden=_orden_real(subtotal_amount=900, total_amount=900))

    assert 200 <= resp.status_code < 300
    assert _restante(checkout) == 0
    assert Movimiento.objects.count() == 0


def test_la_metadata_del_checkout_llega_en_la_orden(client, make_account):
    """Polar no lo documenta, pero el pago real trajo `chart_id` y `account_id`
    intactos: el respaldo para resolver la cuenta cuando falta la fila de
    checkout funciona de verdad."""
    cuenta = make_account()

    _entregar(client, orden=_orden_real(
        checkout_id="chk_sin_fila", metadata={"account_id": str(cuenta.pk)},
    ))

    assert _restante(cuenta) == 1
