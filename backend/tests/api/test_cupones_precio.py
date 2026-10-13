"""`cupones.precio_final`: la única fuente del precio con cupón.

La consumen el admin (preview), el endpoint público, el checkout y el webhook.
Devuelve centavos enteros, redondeados como Stripe con `percent_off` (al más
cercano, mitad hacia arriba): es lo que cobra, y el webhook exige igualdad.
"""
import pytest

from api.catalogo import CATALOGO
from api import cupones
from api.cupones import precio_final


@pytest.mark.parametrize(
    "precio,porcentaje,final,descuento",
    [
        (2900, 30, 2030, 870),
        (2900, 50, 1450, 1450),
        (12500, 30, 8750, 3750),
        (2900, 100, 0, 2900),
        # BRL, MEDIDO en sandbox el 13-10-2026: Stripe redondea al más
        # cercano con la mitad hacia arriba (373,5 → 374; 124,5 → 125).
        (2490, 15, 2116, 374),
        (2490, 5, 2365, 125),
        (2490, 30, 1743, 747),
    ],
)
def test_precio_final_redondea_como_stripe(precio, porcentaje, final, descuento):
    assert precio_final(precio, porcentaje) == (final, descuento)
    assert final + descuento == precio


@pytest.fixture
def cupon_30(db):
    from api.models import Cupon

    return Cupon.objects.create(
        codigo="TREINTA", porcentaje=30, productos=["informe_natal"], usos_maximos=10,
    )


def test_precio_y_descuento_en_la_moneda_pedida(cupon_30):
    """`cupon_30`: 30 % sobre informe_natal (fixture de este archivo)."""
    assert cupones.precio_y_descuento("informe_natal", cupon_30, "brl") == (14900, 4470)
    assert cupones.precio_y_descuento("informe_natal", cupon_30, "usd") == (2900, 870)
    assert cupones.precio_y_descuento("informe_natal", None, "brl") == (14900, 0)


def test_para_todo_porcentaje_y_producto_el_descuento_cabe_en_aplicar_compra():
    """`canje.aplicar_compra` exige `0 <= descuento <= precio` y
    `monto == precio - descuento`: el par que devolvemos tiene que cumplirlo
    siempre, o el webhook rechaza un pago real."""
    for prod in CATALOGO.values():
        for porcentaje in range(1, 101):
            final, descuento = precio_final(prod.precio_en("usd"), porcentaje)
            assert 0 <= descuento <= prod.precio_en("usd")
            assert final + descuento == prod.precio_en("usd")


@pytest.mark.parametrize("porcentaje", [0, 101, -1])
def test_un_porcentaje_fuera_de_1_a_100_se_rechaza(porcentaje):
    with pytest.raises(ValueError):
        precio_final(2900, porcentaje)
