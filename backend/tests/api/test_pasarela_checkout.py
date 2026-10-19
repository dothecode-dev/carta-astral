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


def test_la_fila_nace_en_usd_y_su_precio_de_lista_sigue_su_moneda(make_account):
    from api.models import PasarelaCheckout

    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_x", account=make_account(), codigo_producto="informe_natal",
    )
    assert fila.moneda == "usd"
    assert fila.precio_de_lista() == 2900

    fila.moneda = "brl"
    assert fila.precio_de_lista() == 14900  # sin precio congelado cae al catálogo EN SU moneda

    fila.precio_centavos = 777
    assert fila.precio_de_lista() == 777


def test_filas_existentes_quedan_en_stripe(make_account):
    """Todo código que crea la fila sin decir pasarela (y toda fila anterior a
    Mercado Pago) es de Stripe: el default es lo que no rompe el cobro actual."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_test_5", account=make_account(), codigo_producto="informe_natal",
    )

    assert fila.pasarela == "stripe"
    assert PasarelaCheckout.STRIPE == "stripe"
    assert PasarelaCheckout.MERCADOPAGO == "mercadopago"
    assert fila.mp_preferencia_id == ""
    assert fila.mail_comprador == ""


def test_pasarela_invalida_no_se_guarda(make_account):
    """La validación de modelo la rechaza, y el CheckConstraint también cuando
    alguien guarda directo sin pasar por `full_clean`."""
    from django.core.exceptions import ValidationError
    from django.db import IntegrityError, transaction

    cuenta = make_account()
    fila = PasarelaCheckout(
        checkout_id="cs_test_6", account=cuenta, codigo_producto="informe_natal",
        pasarela="polar",
    )
    with pytest.raises(ValidationError):
        fila.full_clean()

    with pytest.raises(IntegrityError), transaction.atomic():
        fila.save()
