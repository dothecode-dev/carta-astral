"""Cupones de descuento: el precio con cupón y, más adelante, su validación.

Un cupón es un porcentaje sobre el precio de lista de uno o más productos del
catálogo. Para los porcentajes parciales el tope de usos lo aplica Stripe
(Coupon + Promotion Code); acá vive lo que es nuestro: cuánto queda cada
producto, y que ese número sea el mismo en el admin, en la página de precios,
al abrir el checkout y al validar el pago.
"""
import logging
import uuid

from django.db import transaction
from django.utils import timezone

from api import stripe_client
from api.canje import aplicar_compra
from api.catalogo import producto
from api.models import Cupon, CuponUso, PasarelaCheckout

logger = logging.getLogger(__name__)

#: Cuántas veces puede usar cada cuenta un mismo cupón. Constante y no campo:
#: en los dos casos reales vale 1, y como el uso sobrevive al borrado de la
#: cuenta sin la cuenta (SET_NULL), no se puede garantizar más que como
#: mejor esfuerzo. Un campo configurable prometería lo que no cumple.
USOS_POR_CUENTA = 1

MOTIVOS = ("inexistente", "inactivo", "vencido", "no_aplica", "agotado", "ya_usado")


class NoSePuedeReactivar(Exception):
    """Stripe no deja volver a prender un cupón agotado o vencido."""


class CuponInvalido(Exception):
    """El cupón no sirve para este producto / esta cuenta, y por qué."""

    def __init__(self, motivo: str):
        assert motivo in MOTIVOS, motivo
        super().__init__(motivo)
        self.motivo = motivo


def motivo_publico(motivo: str) -> str:
    """Lo que se responde hacia afuera. `inexistente` e `inactivo` se funden
    en `invalido`: el endpoint de validación es público, y decir «existe pero
    está apagado» es regalar el diccionario de códigos vivos."""
    return "invalido" if motivo in ("inexistente", "inactivo") else motivo


def validar(codigo: str, codigo_producto: str, account=None, ahora=None) -> Cupon:
    """El cupón, si sirve para ese producto (y esa cuenta). Si no, `CuponInvalido`.

    Para 1..99 % la autoridad del tope es Stripe; el conteo local es la
    aproximación que evita abrir un checkout que Stripe va a rechazar.
    """
    cupon = Cupon.objects.filter(codigo=Cupon.normalizar(codigo)).first()
    if cupon is None:
        raise CuponInvalido("inexistente")
    _chequear(cupon, codigo_producto, account, ahora or timezone.now())
    return cupon


def _chequear(cupon: Cupon, codigo_producto: str, account, ahora) -> None:
    if not cupon.activo:
        raise CuponInvalido("inactivo")
    if cupon.vencido(ahora):
        raise CuponInvalido("vencido")
    if codigo_producto not in cupon.productos:
        raise CuponInvalido("no_aplica")
    # `ya_usado` antes que `agotado`: con un cupón de un uso las dos cosas son
    # ciertas a la vez, y a quien ya lo usó le sirve más saber eso.
    if account is not None and cupon.usos.filter(account=account).count() >= USOS_POR_CUENTA:
        raise CuponInvalido("ya_usado")
    if cupon.usos_confirmados() >= cupon.usos_maximos:
        raise CuponInvalido("agotado")


def canjear_gratis(account, cupon: Cupon, codigo_producto: str, carta, locale: str) -> PasarelaCheckout:
    """El cupón del 100 %: otorga, deja el checkout acreditado y registra el
    uso, todo en una transacción y sin Stripe.

    Es el ÚNICO camino que toma un lock sobre `Cupon`, y lo toma antes de que
    `aplicar_compra` tome el de `Account`: orden fijo Cupón → Cuenta, para
    que no haya un ABBA con el webhook (que no bloquea `Cupon` nunca). Bajo el
    lock se vuelve a chequear tope y uso por cuenta: es lo que hace que veinte
    pedidos a la vez sobre un cupón de cinco otorguen cinco.

    Lo que sigue al commit —avisar, medir, arrancar el informe— lo hace quien
    llama, fuera de la transacción, igual que `_acreditar` en el webhook.
    """
    prod = producto(codigo_producto)
    with transaction.atomic():
        cupon = Cupon.objects.select_for_update().get(pk=cupon.pk)
        _chequear(cupon, codigo_producto, account, timezone.now())
        checkout_id = f"cupon_{uuid.uuid4().hex}"
        external_id = f"cupon:{checkout_id}"
        aplicar_compra(
            account, codigo_producto, 0, external_id, chart=carta,
            descuento_centavos=prod.precio_centavos, origen="cupon",
        )
        fila = PasarelaCheckout.objects.create(
            checkout_id=checkout_id, account=account, codigo_producto=codigo_producto,
            chart=carta, locale=locale, acreditado_at=timezone.now(),
            cupon=cupon, descuento_centavos=prod.precio_centavos,
        )
        CuponUso.objects.create(
            cupon=cupon, account=account, codigo_producto=codigo_producto,
            descuento_centavos=prod.precio_centavos, monto_pagado_centavos=0,
            checkout=fila, external_id=external_id,
        )
    logger.info("cupón %s canjeado gratis por acc=%s: %s", cupon.codigo, account.pk, codigo_producto)
    return fila


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
