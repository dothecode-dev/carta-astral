"""Mercado Pago en pesos: reclamos y contracargos (RF12)."""

import logging

from api import cobro, devoluciones
from api.models import PasarelaCheckout
from api.pasarelas import mercadopago_api
from api.pasarelas.mercadopago_pagos import _MONEDA, _centavos

logger = logging.getLogger(__name__)


class ContracargoSinCompra(Exception):
    """Un contracargo sobre un pago que no acreditó ninguna fila de MP. Se pide
    el reintento (la fila puede no estar commiteada), pero el aviso es la red:
    MP no reintentó tarde tras un 500 en el sandbox."""


def procesar_reclamo(claim_id: str) -> None:
    """Un reclamo (`topic_claims_integration_wh`) no toca nada: se avisa para
    seguirlo en el panel. Si se convierte en mediación o contracargo, llega por
    el pago (`in_mediation`) o por el tópico de contracargos."""
    if not claim_id:
        logger.error("reclamo de mercadopago sin id en el cuerpo")
        cobro.avisar("Reclamo de Mercado Pago SIN ID en la notificación: revisarlo en el panel de MP.")
        return
    logger.warning("reclamo de mercadopago %s", claim_id)
    cobro.avisar(f"Reclamo de Mercado Pago {claim_id}: no se cambió nada. Seguirlo en el panel de MP.")


def procesar_contracargo(chargeback_id: str, payment_id: str) -> None:
    """Un contracargo se trata como una disputa de Stripe que retira fondos:
    revoca lo que queda, bloquea el mail y avisa (`cobro.disputa_abierta`).

    El cuerpo de la notificación no está firmado (la firma cubre el uuid de la
    query): el contracargo se lee de la API y el pago tiene que figurar en él.

    Lo definitivo vuelve sin levantar (200). Levantan, para reintentar:
    `MPError` al leer el contracargo y `ContracargoSinCompra`.
    """
    if not chargeback_id or not payment_id:
        # Un reintento no agrega el campo que falta.
        logger.error("contracargo de mercadopago sin ids (chargeback=%r, pago=%r)", chargeback_id, payment_id)
        cobro.avisar(
            f"Contracargo de Mercado Pago con la notificación incompleta (contracargo={chargeback_id or '?'}, "
            f"pago={payment_id or '?'}). No se hizo nada: revisarlo en el panel de MP.",
        )
        return

    if not mercadopago_api.id_valido(chargeback_id):
        # Un reintento trae el mismo id: definitivo, no se pregunta a MP.
        _contracargo_a_mano(chargeback_id, payment_id, "el id del contracargo no es válido")
        return
    try:
        contracargo = mercadopago_api.obtener_contracargo(chargeback_id)
    except (mercadopago_api.MPError, mercadopago_api.MPNoConfigurado) as e:
        status = getattr(e, "status", None)
        if status is not None and (200 <= status < 300 or (400 <= status < 500 and status not in (408, 429))):
            # Definitivo: MP contestó 2xx con algo que no es un objeto, o un 4xx
            # que reintentar no cambia (p. ej. 404: el contracargo no es de
            # nuestra cuenta, cuerpo falsificado o reenviado).
            _contracargo_a_mano(chargeback_id, payment_id, f"la API respondió {status} ({e})")
            return
        # Transitorio (red, timeout, 5xx, 408, 429, sin token): 500 para que MP
        # reintente. MP no reintenta tarde (medido en sandbox): se avisa igual.
        logger.error("contracargo de mercadopago %s: MP falló (%s), se pide reintento", chargeback_id, type(e).__name__)
        cobro.avisar(
            f"Contracargo de Mercado Pago {chargeback_id} (pago {payment_id}): no se pudo leer de MP "
            f"({type(e).__name__}, status {status or '-'}). Se pidió reintento; si no llega, revisar a mano.",
        )
        raise
    problema = _forma_invalida(contracargo)
    if problema:
        _contracargo_a_mano(chargeback_id, payment_id, problema)
        return
    pagos = {str(p) for p in contracargo["payments"]}
    if payment_id not in pagos:
        logger.error("contracargo %s no incluye el pago %s (payments=%r)", chargeback_id, payment_id, sorted(pagos))
        cobro.avisar(
            f"Contracargo de Mercado Pago {chargeback_id}: la notificación dice el pago {payment_id} y la "
            f"API no lo incluye ({', '.join(sorted(pagos)) or 'ninguno'}). No se hizo nada: revisar a mano.",
        )
        return

    fila = PasarelaCheckout.objects.filter(
        pasarela=PasarelaCheckout.MERCADOPAGO, pago_id=payment_id,
    ).first()
    if fila is None:
        logger.error("contracargo %s sobre el pago %s sin compra: se pide reintento", chargeback_id, payment_id)
        cobro.avisar(
            f"Contracargo de Mercado Pago {chargeback_id} sobre el pago {payment_id} SIN COMPRA conocida. "
            "No se revocó nada: revisar.",
        )
        raise ContracargoSinCompra(chargeback_id)

    monto = _centavos(contracargo["amount"])
    moneda = contracargo["currency"].lower()
    pagado = devoluciones.pagado(fila)
    if moneda == fila.moneda and monto > pagado:
        # Un contracargo por más de lo que se cobró no es creíble.
        _contracargo_a_mano(
            chargeback_id, payment_id, f"el monto ({monto} centavos) supera lo pagado ({pagado}) en {fila.checkout_id}",
        )
        return

    dispute_id = f"mp:chargeback:{chargeback_id}"
    # La moneda del contracargo, no la de la fila: si no coinciden, `disputas`
    # registra y bloquea sin comparar montos ni revocar.
    aplicada = cobro.disputa_abierta(
        fila, dispute_id=dispute_id, monto=monto, moneda=moneda, motivo="contracargo MP",
    )
    if not aplicada:
        # D3 (spec de cobro en pesos): qué campos dicen que un contracargo se
        # resolvió a favor no se pudo medir en el sandbox, así que la
        # resolución no se automatiza. Toda notificación posterior de un
        # contracargo ya registrado —reenvío, cambio de etapa o resolución—
        # sólo avisa.
        logger.warning("contracargo %s ya registrado sobre %s: se avisa", chargeback_id, fila.checkout_id)
        cobro.avisar(
            f"Contracargo de Mercado Pago {chargeback_id} ({fila.checkout_id}) ya registrado: llegó otra "
            f"notificación (etapa {contracargo.get('stage') or '?'}). No se cambió nada: revisar a mano en MP."
        )


def _forma_invalida(contracargo) -> str:
    """Qué tiene de raro la respuesta de `GET /v1/chargebacks/{id}`, o "".

    La forma es la documentada (V4: el sandbox no simula contracargos). Ante
    cualquier otra no se revoca nada: un monto ausente o en cero revocaría
    anotando 0, y un `payments` de otra forma no prueba que el pago sea éste."""
    if not isinstance(contracargo, dict):
        return f"la API devolvió {type(contracargo).__name__}, no un objeto"
    pagos = contracargo.get("payments")
    if not isinstance(pagos, list) or not all(
        isinstance(p, (str, int)) and not isinstance(p, bool) for p in pagos
    ):
        return f"`payments` con una forma inesperada ({pagos!r})"
    monto = contracargo.get("amount")
    if isinstance(monto, bool) or not isinstance(monto, (int, float, str)):
        return f"`amount` inválido ({monto!r})"
    try:
        centavos = _centavos(monto)
    except (ValueError, OverflowError):  # texto, nan, inf
        return f"`amount` inválido ({monto!r})"
    if centavos <= 0:
        return f"`amount` no positivo ({monto!r})"
    moneda = contracargo.get("currency")
    if not isinstance(moneda, str) or not _MONEDA.fullmatch(moneda):
        return f"`currency` inválida ({moneda!r})"
    return ""


def _contracargo_a_mano(chargeback_id: str, payment_id: str, problema: str) -> None:
    logger.error("contracargo de mercadopago %s (pago %s): %s", chargeback_id, payment_id, problema)
    cobro.avisar(
        f"Contracargo de Mercado Pago {chargeback_id} (pago {payment_id}): {problema}. "
        "No se revocó nada: revisar a mano en MP.",
    )
