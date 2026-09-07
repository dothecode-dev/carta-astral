"""Cupones de descuento: el precio con cupón y, más adelante, su validación.

Un cupón es un porcentaje sobre el precio de lista de uno o más productos del
catálogo. Para los porcentajes parciales el tope de usos lo aplica Stripe
(Coupon + Promotion Code); acá vive lo que es nuestro: cuánto queda cada
producto, y que ese número sea el mismo en el admin, en la página de precios,
al abrir el checkout y al validar el pago.
"""


def precio_final(precio_centavos: int, porcentaje: int) -> tuple[int, int]:
    """`(final, descuento)` en centavos, exactos, para un porcentaje entero.

    Es lo que Stripe cobra con `percent_off`: no se redondea al dólar, y como
    los precios del catálogo son múltiplos de 100 no hay fracción de centavo
    que perder. Siempre `final + descuento == precio`, que es lo que
    `canje.aplicar_compra` exige para acreditar.
    """
    if not 1 <= porcentaje <= 100:
        raise ValueError(f"porcentaje fuera de 1..100: {porcentaje}")
    descuento = precio_centavos * porcentaje // 100
    return precio_centavos - descuento, descuento
