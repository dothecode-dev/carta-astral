"""`cupones.precio_final`: la única fuente del precio con cupón.

La consumen el admin (preview), el endpoint público, el checkout y el webhook.
Devuelve centavos exactos, sin redondear al dólar: es lo que Stripe cobra con
`percent_off`, y como los precios del catálogo son múltiplos de 100, con un
porcentaje entero nunca hay fracción de centavo.
"""
import pytest

from api.catalogo import CATALOGO
from api.cupones import precio_final


@pytest.mark.parametrize(
    "precio,porcentaje,final,descuento",
    [
        (2900, 30, 2030, 870),
        (7900, 30, 5530, 2370),
        (12500, 30, 8750, 3750),
        (2900, 50, 1450, 1450),
        (7900, 50, 3950, 3950),
        (12500, 50, 6250, 6250),
        (2900, 100, 0, 2900),
        (7900, 100, 0, 7900),
        (12500, 100, 0, 12500),
        (2900, 1, 2871, 29),
        (2900, 99, 29, 2871),
    ],
)
def test_tabla_de_precios_con_cupon(precio, porcentaje, final, descuento):
    assert precio_final(precio, porcentaje) == (final, descuento)


def test_para_todo_porcentaje_y_producto_el_descuento_cabe_en_aplicar_compra():
    """`canje.aplicar_compra` exige `0 <= descuento <= precio` y
    `monto == precio - descuento`: el par que devolvemos tiene que cumplirlo
    siempre, o el webhook rechaza un pago real."""
    for prod in CATALOGO.values():
        for porcentaje in range(1, 101):
            final, descuento = precio_final(prod.precio_centavos, porcentaje)
            assert 0 <= descuento <= prod.precio_centavos
            assert final + descuento == prod.precio_centavos


@pytest.mark.parametrize("porcentaje", [0, 101, -1])
def test_un_porcentaje_fuera_de_1_a_100_se_rechaza(porcentaje):
    with pytest.raises(ValueError):
        precio_final(2900, porcentaje)
