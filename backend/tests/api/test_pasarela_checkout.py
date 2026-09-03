"""El modelo que ata una sesión de pago a una cuenta.

Se llamaba `PolarCheckout`. El nombre nuevo es de la pasarela en general y no
de Stripe: es la fila que guarda lo que la pasarela no sabe —de quién es la
compra, sobre qué carta y en qué idioma—, y eso no cambia si la pasarela cambia.
"""

import pytest

from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db


def test_el_payment_intent_arranca_vacio_y_resuelve_el_reembolso(make_account):
    """`refund.created` no trae el id de la sesión, sólo el `payment_intent`:
    sin guardarlo al acreditar no hay forma de saber a qué compra corresponde."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_test_2", account=make_account(), codigo_producto="informe_natal",
    )
    assert fila.payment_intent == ""

    fila.payment_intent = "pi_abc"
    fila.save(update_fields=["payment_intent"])

    assert PasarelaCheckout.objects.get(payment_intent="pi_abc").pk == fila.pk


def test_dos_compras_sin_payment_intent_conviven(make_account):
    """El campo no es único: mientras el webhook no acredite queda vacío en
    todas las filas abiertas, y un índice único las haría chocar entre sí."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(
        checkout_id="cs_test_3", account=cuenta, codigo_producto="informe_natal",
    )
    PasarelaCheckout.objects.create(
        checkout_id="cs_test_4", account=cuenta, codigo_producto="informe_natal",
    )

    assert PasarelaCheckout.objects.filter(payment_intent="").count() == 2
