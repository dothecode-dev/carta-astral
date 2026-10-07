"""«Pagar es entrar» (spec docs/2026-10-07-spec-pagar-es-entrar.md).

Los momentos de una compra sin cuenta, en un solo módulo para que la regla
de seguridad viva en un lugar: nunca se abre sesión en una cuenta que existía
antes de la compra, y el checkout_id solo nunca alcanza para entrar.
"""

import logging
import secrets

from django.db import transaction

from api import cupones, stripe_client
from api.chart_service import create_chart
from api.identity import hash_token, tombstone_hmac_configurada
from api.models import PasarelaCheckout

logger = logging.getLogger(__name__)
PRODUCTO = "informe_natal"


class CuponNoAdmitido(Exception):
    """Un cupón del 100 % se canjea sin Stripe: sin cuenta no hay a quién dárselo."""


class NoDisponible(Exception):
    """Falta configuración que el webhook va a necesitar: mejor no cobrar."""


def abrir(datos: dict, locale: str, codigo_cupon: str | None):
    """Crea la carta sin dueño, abre la sesión de Stripe y guarda la fila.

    Devuelve `(fila, nonce_en_claro)`; en la base sólo queda el hash del nonce.
    `datos` ya viene validado por la vista. La carta y la llamada a Stripe van
    en el mismo átomo para que un fallo de Stripe no deje una carta sin dueño;
    una sesión de Stripe huérfana (si la base falla después) vence sola a la hora.
    """
    if not tombstone_hmac_configurada():
        raise NoDisponible("TOMBSTONE_HMAC_KEY")
    cupon = None
    if codigo_cupon:
        cupon = cupones.validar(codigo_cupon, PRODUCTO, account=None)
        if cupon.porcentaje >= 100:
            raise CuponNoAdmitido
    nonce = secrets.token_urlsafe(32)
    with transaction.atomic():
        carta = create_chart(datos, account=None)
        checkout_id, url = stripe_client.crear_checkout(
            None, PRODUCTO, chart=carta, locale=locale, cupon=cupon, terminos=True,
        )
        precio, descuento = cupones.precio_y_descuento(PRODUCTO, cupon)
        fila = PasarelaCheckout.objects.create(
            checkout_id=checkout_id, account=None, codigo_producto=PRODUCTO, chart=carta,
            locale=locale, cupon=cupon, descuento_centavos=descuento, url=url,
            precio_centavos=precio, anonimo=True, nonce_hash=hash_token(nonce),
        )
    return fila, nonce
