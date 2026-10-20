"""Abrir un pago: el único camino, con cuenta y sin cuenta (R8).

El dominio decide lo que no es de ninguna pasarela —el precio y el descuento,
que se congelan en la fila— y la moneda elige quién abre la sesión. Las
validaciones del pedido (producto, cupón, mail, mantenimiento) ya las hizo la
vista; acá llega un pedido válido.
"""

from api import catalogo, cupones
from api.models import PasarelaCheckout
from api.pasarelas import mercadopago, mercadopago_api
from api.pasarelas import stripe as pasarela_stripe

# Las de MP salen del cliente HTTP y no de `mercadopago`: ese módulo llega
# hasta acá por `cobro` → `compra_anonima`, y a mitad de su import todavía no
# tiene atributos que leer.
ERRORES_STRIPE = pasarela_stripe.ERRORES
ERRORES_MP = (mercadopago_api.MPNoConfigurado, mercadopago_api.MPError)
#: Lo que una vista atrapa con un solo `except`: configuración o API de una pasarela.
ERRORES_DE_PASARELA = ERRORES_STRIPE + ERRORES_MP
STRIPE_NO_CONFIGURADO = pasarela_stripe.NoConfigurado
CUPON_RECHAZADO = pasarela_stripe.CuponRechazado


def abrir_checkout(
    account, codigo: str, *, sujeto, locale: str, moneda: str, cupon=None, mail: str = "",
    anonimo: bool = False, nonce_hash: str = "",
) -> PasarelaCheckout:
    """Abre la sesión o preferencia y devuelve su fila.

    `KeyError` si el producto no existe o no se vende en `moneda`, `ValueError`
    si es gratis o está retirado, y `ERRORES_DE_PASARELA` si la pasarela no abre.
    En pesos `mail` es a quien se le entrega (MP no devuelve el de quien paga);
    en Stripe el mail lo pide el checkout y acá no se usa.
    """
    en_pesos = catalogo.pasarela_de(moneda) == "mercadopago"
    if en_pesos and cupon is not None:
        # Fase 1: la vista ya lo rechaza. Si llegara, se congelaría un
        # descuento que la preferencia no aplica.
        raise ValueError("sin cupones en pesos")
    precio, descuento = cupones.precio_y_descuento(codigo, cupon, moneda)
    if en_pesos:
        return mercadopago.abrir(
            account, codigo, sujeto=sujeto, locale=locale, moneda=moneda, precio=precio,
            descuento=descuento, mail=mail, anonimo=anonimo, nonce_hash=nonce_hash,
        )
    return pasarela_stripe.abrir(
        account, codigo, sujeto=sujeto, locale=locale, moneda=moneda, precio=precio,
        descuento=descuento, cupon=cupon, anonimo=anonimo, nonce_hash=nonce_hash,
    )
