"""Stripe: abrir la sesión de pago y guardar su fila.

El precio y el descuento llegan ya congelados por `apertura`; acá sólo se abre
la sesión y se deja constancia. Los errores de `stripe_client` se propagan:
los traduce la vista.
"""

from api import stripe_client
from api.models import PasarelaCheckout

#: Lo que `abrir` deja escapar cuando Stripe no abre la sesión.
ERRORES = (stripe_client.StripeNoConfigurado, stripe_client.StripeError)
NoConfigurado = stripe_client.StripeNoConfigurado
CuponRechazado = stripe_client.CuponRechazado


def abrir(
    cuenta, codigo: str, *, sujeto, locale: str, moneda: str, precio: int, descuento: int,
    cupon=None, anonimo: bool = False, nonce_hash: str = "",
) -> PasarelaCheckout:
    """Sin cuenta, la sesión lleva la casilla obligatoria de los términos."""
    extra = {"terminos": True} if anonimo else {"cupon": cupon}
    checkout_id, url = stripe_client.crear_checkout(
        cuenta, codigo, sujeto=sujeto, locale=locale, moneda=moneda, **extra,
    )
    # Después del éxito y no antes: una fila huérfana dejaría que el webhook
    # de otra orden resolviera contra ella. Es contra el precio congelado acá
    # que el webhook valida lo que Stripe cobró, aunque el catálogo cambie
    # mientras la sesión sigue viva.
    return PasarelaCheckout.objects.create(
        checkout_id=checkout_id, account=cuenta, pasarela=PasarelaCheckout.STRIPE, codigo_producto=codigo,
        sujeto=sujeto, locale=locale, cupon=cupon, descuento_centavos=descuento, url=url,
        precio_centavos=precio, moneda=moneda, anonimo=anonimo, nonce_hash=nonce_hash,
    )
