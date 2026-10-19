"""Mercado Pago en pesos: abrir el pago (la preferencia y su fila) y traducir
lo que MP dice de un pago a los verbos de `cobro` (RF11).

Mismo papel que `stripe_client.crear_checkout` más la creación de la fila de
`PasarelaCheckout` que hoy hace la vista, porque acá el `checkout_id` lo
generamos nosotros (`external_reference`) y tiene que existir antes de abrir
la preferencia. Los errores del cliente HTTP (`MPError`, `MPNoConfigurado`)
se propagan: los traduce la vista.
"""

import logging
import secrets

from django.conf import settings
from django.utils import timezone

from api import cobro, cupones, stripe_client
from api.conteo import contar
from api.models import PasarelaCheckout
from api.pasarelas import mercadopago_api

logger = logging.getLogger(__name__)

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


class FilaInexistente(Exception):
    """Un pago con nuestro prefijo (`mp_`) y sin fila. No debería pasar —la fila
    se crea antes de abrir la preferencia—, así que se pide el reintento."""


#: Estados de un reembolso de MP que no devolvieron plata (todavía o nunca).
_REEMBOLSO_SIN_EFECTO = {"rejected", "cancelled", "in_process", "pending"}


def _centavos(monto) -> int:
    """MP informa montos en unidades con decimales (float): siempre `round`,
    nunca `int`, que trunca 19999.99 * 100 a 1999998."""
    return round(float(monto or 0) * 100)


def procesar_pago(payment_id: str) -> None:
    """Lee el pago de la API —no se confía en el cuerpo de la notificación— y
    lo traduce a `cobro`.

    Lo definitivo vuelve sin levantar (el webhook responde 200); lo que levanta
    es para reintentar: `MPError` al leer el pago, `FilaInexistente`,
    `cobro.CompraAnonimaSinMail` o cualquier fallo inesperado.
    """
    pago = mercadopago_api.obtener_pago(payment_id)
    referencia = pago.get("external_reference") or ""
    if not referencia.startswith("mp_"):
        # Review Focus 1: la cuenta de MP puede cobrar otras cosas.
        logger.info("pago de mercadopago %s ajeno (external_reference=%r): se ignora", payment_id, referencia)
        return
    fila = PasarelaCheckout.objects.filter(checkout_id=referencia).first()
    if fila is None:
        logger.error("pago de mercadopago %s con referencia %s sin fila: se pide reintento", payment_id, referencia)
        raise FilaInexistente(referencia)
    pago_id = str(pago.get("id") or payment_id)
    if fila.pasarela != PasarelaCheckout.MERCADOPAGO:
        logger.error("pago de mercadopago %s sobre la fila %s de %s", pago_id, fila.checkout_id, fila.pasarela)
        cobro.avisar(
            f"Pago de Mercado Pago {pago_id} con referencia {fila.checkout_id}, que es una compra de "
            f"{fila.pasarela}. No se hizo nada: revisar.",
        )
        return

    estado = pago.get("status") or ""
    moneda = (pago.get("currency_id") or "").lower()
    if estado == "approved":
        _acreditar(fila, pago, pago_id, moneda)
    elif estado == "in_mediation":
        # R12: un reclamo del comprador. Hasta que MP lo resuelva no se toca nada.
        logger.warning("pago de mercadopago %s (%s) en mediación", pago_id, fila.checkout_id)
        cobro.avisar(
            f"Pago de Mercado Pago {pago_id} ({fila.checkout_id}) en MEDIACIÓN: el comprador abrió un "
            "reclamo. No se cambió nada: seguirlo en el panel de MP.",
        )
    elif estado not in ("refunded", "partially_refunded"):
        logger.info("pago de mercadopago %s (%s) en estado %s: nada que hacer", pago_id, fila.checkout_id, estado)

    if estado in ("approved", "refunded", "partially_refunded"):
        # Un reembolso parcial deja el pago `approved` (status_detail
        # `partially_refunded`): los reembolsos se miran en los tres estados.
        _reembolsar(fila, pago, pago_id, moneda)


def _acreditar(fila: PasarelaCheckout, pago: dict, pago_id: str, moneda: str) -> None:
    try:
        cobro.acreditar(
            fila, pago_id=pago_id, monto_pagado=_centavos(pago.get("transaction_amount")), moneda=moneda,
            medio=pago.get("payment_type_id") or "", external_id=f"mp:payment:{pago_id}",
        )
    except cobro.PagoDuplicado:
        # RF11b. El chequeo vive en `cobro`, bajo el lock de la fila: hacerlo
        # acá, antes, dejaba que dos pagos concurrentes acreditaran los dos.
        _reembolsar_duplicado(fila, pago_id)
    except cobro.CompraDisputada as e:
        cobro.avisar(
            f"Pago de Mercado Pago {pago_id} ({fila.checkout_id}) aprobado sobre una compra con la "
            f"disputa {e}. No se entregó nada.",
        )


def _reembolsar_duplicado(fila: PasarelaCheckout, pago_id: str) -> None:
    try:
        mercadopago_api.reembolsar(pago_id, f"mp:duplicado:{pago_id}")
    except (mercadopago_api.MPError, mercadopago_api.MPNoConfigurado) as e:
        # Sin reintento: repetiría toda la notificación. El aviso es la red.
        logger.error("no se pudo reembolsar el pago duplicado %s (%s): %s", pago_id, fila.checkout_id, e)
        cobro.avisar(
            f"Pago de Mercado Pago {pago_id} DUPLICADO sobre {fila.checkout_id} (ya la acreditó el pago "
            f"{fila.payment_intent or '?'}): NO se pudo reembolsar ({e}). Reembolsarlo a mano en MP.",
        )
        return
    logger.warning("pago duplicado %s sobre %s reembolsado", pago_id, fila.checkout_id)
    cobro.avisar(
        f"Pago de Mercado Pago {pago_id} DUPLICADO sobre {fila.checkout_id}: no se acreditó y se "
        "pidió su reembolso.",
    )


def _reembolsar(fila: PasarelaCheckout, pago: dict, pago_id: str, moneda: str) -> None:
    for reembolso in pago.get("refunds") or []:
        refund_id = str(reembolso.get("id") or "")
        estado = reembolso.get("status")
        if estado in _REEMBOLSO_SIN_EFECTO:
            logger.info("reembolso %s del pago %s en estado %s: no se revoca", refund_id, pago_id, estado)
            continue
        cobro.reembolsar(
            fila, pago_id=pago_id, refund_id=refund_id, monto=_centavos(reembolso.get("amount")),
            moneda=moneda, external_id=f"mp:refund:{refund_id}" if refund_id else "",
        )
