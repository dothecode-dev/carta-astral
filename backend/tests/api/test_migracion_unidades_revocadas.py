"""La 0057 completa `unidades_revocadas` en las compras con reembolsos previos."""

import importlib

import pytest
from django.apps import apps

from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db

migracion = importlib.import_module("api.migrations.0057_unidades_revocadas_existentes")


def _fila(checkout_id, codigo, precio, reembolsado, descuento=0):
    return PasarelaCheckout.objects.create(
        checkout_id=checkout_id, codigo_producto=codigo, precio_centavos=precio,
        descuento_centavos=descuento, reembolsado_centavos=reembolsado,
    )


def test_completa_total_parcial_regalo_y_sin_reembolso():
    total = _fila("cs_t", "informe_natal", 500, 500)
    parcial_pack = _fila("cs_p", "pack_5_natal", 12500, 2600)  # ceil(1,04) = 2
    regalo = _fila("cs_r", "pack_5_natal", 12500, 0, descuento=12500)
    sin = _fila("cs_s", "informe_natal", 500, 0)

    migracion.completar(apps, None)

    valores = {f.checkout_id: f.unidades_revocadas for f in PasarelaCheckout.objects.all()}
    assert valores == {total.checkout_id: 1, parcial_pack.checkout_id: 2, regalo.checkout_id: 0, sin.checkout_id: 0}
