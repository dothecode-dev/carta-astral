"""Cupones de descuento: el precio con cupón y, más adelante, su validación.

Un cupón es un porcentaje sobre el precio de lista de uno o más productos del
catálogo. Para los porcentajes parciales el tope de usos lo aplica Stripe
(Coupon + Promotion Code); acá vive lo que es nuestro: cuánto queda cada
producto, y que ese número sea el mismo en el admin, en la página de precios,
al abrir el checkout y al validar el pago.
"""
import logging

from api import stripe_client

logger = logging.getLogger(__name__)


class NoSePuedeReactivar(Exception):
    """Stripe no deja volver a prender un cupón agotado o vencido."""


def publicar(cupon) -> None:
    """Crea el espejo en Stripe de un cupón parcial recién guardado.

    El del 100 % no pasa por Stripe. Idempotente: si ya tiene ids, no crea
    otros. Si Stripe falla, el cupón queda sin ids —sin publicar— y el error
    se propaga para que el admin lo muestre.
    """
    if cupon.porcentaje >= 100 or cupon.stripe_promotion_code_id:
        return
    coupon_id, promo_id = stripe_client.crear_cupon(cupon)
    cupon.stripe_coupon_id = coupon_id
    cupon.stripe_promotion_code_id = promo_id
    cupon.save(update_fields=["stripe_coupon_id", "stripe_promotion_code_id"])


def cambiar_activo(cupon, activo: bool) -> None:
    """Apaga o prende el cupón, primero en Stripe y después acá.

    En ese orden a propósito: si Stripe falla, la fila no cambia, y no queda
    un cupón «activo» acá que Stripe rechaza (o al revés).
    """
    if cupon.stripe_promotion_code_id:
        try:
            stripe_client.activar_cupon(cupon.stripe_promotion_code_id, activo)
        except stripe_client.StripeError as exc:
            if activo:
                raise NoSePuedeReactivar(cupon.codigo) from exc
            raise
    cupon.activo = activo
    cupon.save(update_fields=["activo"])


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
