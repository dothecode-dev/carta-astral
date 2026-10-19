"""Abrir un pago en pesos: la preferencia de Mercado Pago y su fila.

Mismo papel que `stripe_client.crear_checkout` más la creación de la fila de
`PasarelaCheckout` que hoy hace la vista, porque acá el `checkout_id` lo
generamos nosotros (`external_reference`) y tiene que existir antes de abrir
la preferencia. Los errores del cliente HTTP (`MPError`, `MPNoConfigurado`)
se propagan: los traduce la vista.
"""

import secrets

from django.conf import settings
from django.utils import timezone

from api import cupones, stripe_client
from api.conteo import contar
from api.models import PasarelaCheckout
from api.pasarelas import mercadopago_api

#: Nombre que ve quien paga en la pantalla de MP. Fijo y por idioma; lo que no
#: está acá cae al código del producto.
_TITULOS = {
    "informe_natal": {
        "es": "Informe natal ASTRA",
        "en": "ASTRA natal chart report",
        "pt": "Relatório natal ASTRA",
    },
}


def titulo(codigo: str, locale: str) -> str:
    return _TITULOS.get(codigo, {}).get(locale, codigo)


def abrir(
    cuenta, codigo: str, *, sujeto, locale: str, moneda: str, mail: str = "",
    anonimo: bool = False, nonce_hash: str = "",
) -> PasarelaCheckout:
    # Sin cupón en pesos (fase 1): el precio es el de lista.
    precio, descuento = cupones.precio_y_descuento(codigo, None, moneda)
    checkout_id = f"mp_{secrets.token_hex(16)}"
    destino = settings.MP_RETORNO_URL.replace("{locale}", locale).replace("{checkout_id}", checkout_id)
    ahora = timezone.now()
    metadata = {"checkout_id": checkout_id}
    if cuenta is not None:
        metadata["account_id"] = str(cuenta.pk)
    cuerpo: dict = {
        "items": [{
            "id": codigo, "title": titulo(codigo, locale), "quantity": 1,
            "currency_id": moneda.upper(), "unit_price": precio / 100,
        }],
        "external_reference": checkout_id,
        "notification_url": settings.MP_NOTIFICACION_URL,
        "back_urls": {"success": destino, "pending": destino, "failure": destino},
        "auto_return": "approved",
        "expires": True,
        "expiration_date_from": ahora.isoformat(),
        "expiration_date_to": (ahora + stripe_client.VENCIMIENTO_SESION).isoformat(),
        # Sin efectivo ni cajero: tardan días en acreditar y la preferencia vence a la hora.
        "payment_methods": {"excluded_payment_types": [{"id": "ticket"}, {"id": "atm"}], "installments": 1},
        "metadata": metadata,
    }
    if mail:
        cuerpo["payer"] = {"email": mail}

    preferencia = mercadopago_api.crear_preferencia(cuerpo)

    # Después del éxito y no antes: una fila huérfana dejaría que el webhook
    # resolviera contra una preferencia que nunca existió.
    fila = PasarelaCheckout.objects.create(
        checkout_id=checkout_id, account=cuenta, codigo_producto=codigo, sujeto=sujeto,
        locale=locale, descuento_centavos=descuento, precio_centavos=precio, moneda=moneda,
        pasarela=PasarelaCheckout.MERCADOPAGO, mp_preferencia_id=preferencia["id"],
        url=preferencia["init_point"], mail_comprador=mail, anonimo=anonimo, nonce_hash=nonce_hash,
    )
    contar("checkout_abierto")
    return fila
