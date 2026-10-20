"""El modelo que ata una sesión de pago a una cuenta.

Se llamaba `PolarCheckout`. El nombre nuevo es de la pasarela en general y no
de Stripe: es la fila que guarda lo que la pasarela no sabe —de quién es la
compra, sobre qué carta y en qué idioma—, y eso no cambia si la pasarela cambia.
"""

import importlib

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db


def test_el_pago_id_arranca_vacio_y_resuelve_el_reembolso(make_account):
    """`refund.created` no trae el id de la sesión, sólo el `payment_intent`:
    sin guardarlo al acreditar no hay forma de saber a qué compra corresponde."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_test_2", pasarela=PasarelaCheckout.STRIPE, account=make_account(), codigo_producto="informe_natal",
    )
    assert fila.pago_id == ""

    fila.pago_id = "pi_abc"
    fila.save(update_fields=["pago_id"])

    assert PasarelaCheckout.objects.get(pago_id="pi_abc").pk == fila.pk


def test_dos_compras_sin_pago_id_conviven(make_account):
    """El campo no es único: mientras el webhook no acredite queda vacío en
    todas las filas abiertas, y un índice único las haría chocar entre sí."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(
        checkout_id="cs_test_3", pasarela=PasarelaCheckout.STRIPE, account=cuenta, codigo_producto="informe_natal",
    )
    PasarelaCheckout.objects.create(
        checkout_id="cs_test_4", pasarela=PasarelaCheckout.STRIPE, account=cuenta, codigo_producto="informe_natal",
    )

    assert PasarelaCheckout.objects.filter(pago_id="").count() == 2


def test_la_fila_nace_en_usd_y_su_precio_de_lista_sigue_su_moneda(make_account):
    from api.models import PasarelaCheckout

    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_x", pasarela=PasarelaCheckout.STRIPE, account=make_account(), codigo_producto="informe_natal",
    )
    assert fila.moneda == "usd"
    assert fila.precio_de_lista() == 2900

    fila.moneda = "brl"
    assert fila.precio_de_lista() == 14900  # sin precio congelado cae al catálogo EN SU moneda

    fila.precio_centavos = 777
    assert fila.precio_de_lista() == 777


def test_fila_de_stripe_y_constantes_de_pasarela(make_account):
    """Las constantes de pasarela y los campos de MP vacíos en una fila de Stripe."""
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_test_5", pasarela=PasarelaCheckout.STRIPE, account=make_account(), codigo_producto="informe_natal",
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


def test_fila_sin_pasarela_no_se_guarda(make_account):
    """`pasarela` no tiene default: quien crea la fila lo dice, y el CheckConstraint
    rechaza el valor vacío."""
    with pytest.raises(IntegrityError), transaction.atomic():
        PasarelaCheckout.objects.create(
            checkout_id="cs_sin_pasarela", account=make_account(), codigo_producto="informe_natal",
        )


def test_migracion_marca_informe_arrancado_de_stripe_acreditadas(make_account):
    migracion = importlib.import_module("api.migrations.0064_pago_id")
    cuenta = make_account()
    ahora = timezone.now()
    acreditada = PasarelaCheckout.objects.create(
        checkout_id="cs_a", account=cuenta, pasarela=PasarelaCheckout.STRIPE,
        codigo_producto="informe_natal", acreditado_at=ahora,
    )
    abierta = PasarelaCheckout.objects.create(
        checkout_id="cs_b", account=cuenta, pasarela=PasarelaCheckout.STRIPE, codigo_producto="informe_natal",
    )
    # Las de MP las marcó la 0062: esta migración filtra por Stripe y no las toca.
    de_mp = PasarelaCheckout.objects.create(
        checkout_id="mp_a", account=cuenta, pasarela=PasarelaCheckout.MERCADOPAGO,
        codigo_producto="informe_natal", acreditado_at=ahora,
    )

    migracion.marcar_acreditadas(apps, None)

    acreditada.refresh_from_db()
    abierta.refresh_from_db()
    de_mp.refresh_from_db()
    assert acreditada.informe_arrancado_at == acreditada.acreditado_at
    assert abierta.informe_arrancado_at is None
    assert de_mp.informe_arrancado_at is None


def test_pago_id_sigue_en_la_columna_payment_intent():
    """El rename de la 0064 es sólo de estado: el código viejo que atiende
    durante el deploy (o el que queda si el deploy falla) lee `payment_intent`."""
    from django.db import connection

    assert PasarelaCheckout._meta.get_field("pago_id").column == "payment_intent"
    with connection.cursor() as cursor:
        columnas = [c.name for c in connection.introspection.get_table_description(cursor, "api_pasarelacheckout")]
    assert "payment_intent" in columnas and "pago_id" not in columnas
