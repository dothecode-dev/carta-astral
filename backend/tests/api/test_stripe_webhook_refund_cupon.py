"""El reembolso de una compra con cupón prorratea sobre LO PAGADO.

Con el precio de lista como divisor, un pack de 5 al 50 % (paga 6250)
reembolsado entero caía en la rama parcial y revocaba 3: la persona recuperaba
toda la plata y se quedaba con dos informes.
"""
import json

import pytest

from api.canje import aplicar_compra
from api.models import Cupon, Derecho, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_pack": "pack_5_natal", "price_natal": "informe_natal"}


def _entregar(client, amount, pi):
    refund = {"id": f"re_{pi}", "object": "refund", "amount": amount, "currency": "usd",
              "charge": "ch_1", "payment_intent": pi, "status": "succeeded"}
    cuerpo = json.dumps({"id": "evt_r", "type": "refund.created", "data": {"object": refund}}).encode()
    return client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))


def _comprado(cuenta, producto, descuento, pi, porcentaje=50):
    cupon = Cupon.objects.create(codigo=f"C{pi}", porcentaje=porcentaje, productos=[producto], usos_maximos=5)
    fila = PasarelaCheckout.objects.create(checkout_id=f"cs_{pi}", account=cuenta, codigo_producto=producto,
                                           cupon=cupon, descuento_centavos=descuento, payment_intent=pi)
    from api.catalogo import producto as prod
    aplicar_compra(cuenta, producto, prod(producto).precio_centavos - descuento, external_id=f"stripe:session:cs_{pi}",
                   descuento_centavos=descuento)
    return fila


def _restante(cuenta):
    return Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante


def test_un_pack_con_descuento_reembolsado_entero_revoca_los_cinco(client, make_account):
    cuenta = make_account()
    _comprado(cuenta, "pack_5_natal", 6250, "pi_a")
    assert _restante(cuenta) == 5

    _entregar(client, 6250, "pi_a")

    assert _restante(cuenta) == 0


def test_medio_pack_con_descuento_reembolsado_revoca_tres(client, make_account):
    cuenta = make_account()
    _comprado(cuenta, "pack_5_natal", 6250, "pi_b")

    _entregar(client, 3125, "pi_b")

    assert _restante(cuenta) == 2


def test_un_regalo_del_100_con_un_refund_se_revoca_entero_sin_dividir_por_cero(client, make_account):
    cuenta = make_account()
    _comprado(cuenta, "informe_natal", 2900, "pi_c", porcentaje=100)

    r = _entregar(client, 0, "pi_c")

    assert r.status_code == 200
    assert _restante(cuenta) == 0


def test_una_compra_sin_descuento_se_reembolsa_como_antes(client, make_account):
    cuenta = make_account()
    PasarelaCheckout.objects.create(checkout_id="cs_d", account=cuenta, codigo_producto="pack_5_natal", payment_intent="pi_d")
    aplicar_compra(cuenta, "pack_5_natal", 12500, external_id="stripe:session:cs_d")

    _entregar(client, 6250, "pi_d")

    assert _restante(cuenta) == 2
