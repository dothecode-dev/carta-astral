"""La 0065 prefija con `stripe:refund:` los `Reembolso` que Stripe guardó con el id crudo."""

import importlib

import pytest
from django.apps import apps

from api.models import PasarelaCheckout, Reembolso

pytestmark = pytest.mark.django_db

migracion = importlib.import_module("api.migrations.0065_reembolso_stripe_prefijo")


def test_prefija_los_crudos_y_deja_en_paz_al_resto():
    fila = PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id="cs_m", codigo_producto="informe_natal",
    )
    for refund_id in ("re_x", "pyr_z", "stripe:refund:re_y", "stripe:refund:pyr_w", "mp:refund:123"):
        Reembolso.objects.create(refund_id=refund_id, fila=fila, monto=1)

    migracion.prefijar(apps, None)

    assert sorted(Reembolso.objects.values_list("refund_id", flat=True)) == [
        "mp:refund:123", "stripe:refund:pyr_w", "stripe:refund:pyr_z", "stripe:refund:re_x", "stripe:refund:re_y",
    ]
