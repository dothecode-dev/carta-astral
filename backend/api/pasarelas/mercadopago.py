"""Mercado Pago en pesos: abrir el pago (la preferencia y su fila) y traducir
lo que MP dice de un pago a los verbos de `cobro` (RF11).

Mismo papel que `stripe_client.crear_checkout` más la creación de la fila de
`PasarelaCheckout` que hoy hace la vista, porque acá el `checkout_id` lo
generamos nosotros (`external_reference`) y tiene que existir antes de abrir
la preferencia. Los errores del cliente HTTP (`MPError`, `MPNoConfigurado`)
se propagan: los traduce la vista.
"""

import datetime as dt
import logging
import re
import secrets

from django.conf import settings
from django.utils import timezone

from api import cobro, cupones, devoluciones, disputas, stripe_client
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


#: El `external_reference` que genera `abrir`: `mp_` + 32 hex. Otro formato,
#: aunque empiece con `mp_`, es de otra integración de la misma cuenta.
_REFERENCIA_NUESTRA = re.compile(r"mp_[0-9a-f]{32}")

#: Estados conocidos de un reembolso de MP que no devolvieron plata (todavía o
#: nunca). Sólo `approved` revoca; un estado fuera de los dos conjuntos se avisa.
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
    if not isinstance(referencia, str) or not _REFERENCIA_NUESTRA.fullmatch(referencia):
        # Review Focus 1: la cuenta de MP puede cobrar otras cosas.
        logger.info("pago de mercadopago %s ajeno (external_reference=%r): se ignora", payment_id, referencia)
        return
    fila = PasarelaCheckout.objects.filter(checkout_id=referencia).first()
    if fila is None:
        logger.error("pago de mercadopago %s con referencia %s sin fila: se pide reintento", payment_id, referencia)
        # MP no reintenta tarde (medido en sandbox): sin aviso, plata cobrada
        # y nada entregado sin que nadie se entere.
        cobro.avisar(
            f"Pago de Mercado Pago {payment_id} con referencia {referencia} SIN FILA: cobrado y sin "
            "entregar. Revisar.",
        )
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
    elif estado == "charged_back":
        # La revocación la hace el tópico de contracargos (RF12), que llega
        # SÓLO a la URL del panel: si no está suscripto, este aviso es la red.
        logger.warning("pago de mercadopago %s (%s) con contracargo", pago_id, fila.checkout_id)
        cobro.avisar(
            f"Pago de Mercado Pago {pago_id} ({fila.checkout_id}) con CONTRACARGO: revisar a mano y "
            "verificar que el tópico de contracargos esté suscripto en el panel de MP.",
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
        if estado != "approved":
            logger.error("reembolso %s del pago %s en estado desconocido %r: no se revoca", refund_id, pago_id, estado)
            cobro.avisar(
                f"Reembolso {refund_id} del pago de Mercado Pago {pago_id} ({fila.checkout_id}) en un "
                f"estado desconocido ({estado!r}). No se revocó nada: revisar.",
            )
            continue
        if not refund_id:
            # Sin id no hay constancia ni idempotencia posible.
            logger.error("reembolso sin id del pago %s (%s): no se revoca", pago_id, fila.checkout_id)
            cobro.avisar(
                f"Reembolso SIN ID del pago de Mercado Pago {pago_id} ({fila.checkout_id}). "
                "No se revocó nada: resolver a mano.",
            )
            continue
        cobro.reembolsar(
            fila, pago_id=pago_id, refund_id=refund_id, monto=_centavos(reembolso.get("amount")),
            moneda=moneda, external_id=f"mp:refund:{refund_id}",
        )


# --- reclamos y contracargos (RF12) ------------------------------------------------------


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
    revoca lo que queda, bloquea el mail y avisa (`disputas._retirar`).

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
        pasarela=PasarelaCheckout.MERCADOPAGO, payment_intent=payment_id,
    ).first()
    if fila is None:
        logger.error("contracargo %s sobre el pago %s sin compra: se pide reintento", chargeback_id, payment_id)
        cobro.avisar(
            f"Contracargo de Mercado Pago {chargeback_id} sobre el pago {payment_id} SIN COMPRA conocida. "
            "No se revocó nada: revisar.",
        )
        raise ContracargoSinCompra(chargeback_id)

    monto = _centavos(contracargo["amount"])
    pagado = devoluciones.pagado(fila)
    if monto > pagado:
        # Un contracargo por más de lo que se cobró no es creíble.
        _contracargo_a_mano(
            chargeback_id, payment_id, f"el monto ({monto} centavos) supera lo pagado ({pagado}) en {fila.checkout_id}",
        )
        return

    dispute_id = f"mp:chargeback:{chargeback_id}"
    aviso = disputas._retirar(fila.pk, None, dispute_id, monto, "ars", "contracargo MP")
    if aviso is None:
        # D3 (spec de cobro en pesos): qué campos dicen que un contracargo se
        # resolvió a favor no se pudo medir en el sandbox, así que la
        # resolución no se automatiza. Toda notificación posterior de un
        # contracargo ya registrado —reenvío, cambio de etapa o resolución—
        # sólo avisa.
        logger.warning("contracargo %s ya registrado sobre %s: se avisa", chargeback_id, fila.checkout_id)
        aviso = (
            f"Contracargo de Mercado Pago {chargeback_id} ({fila.checkout_id}) ya registrado: llegó otra "
            f"notificación (etapa {contracargo.get('stage') or '?'}). No se cambió nada: revisar a mano en MP."
        )
    # Después del commit de `_retirar`: nunca un aviso de algo que se deshizo.
    cobro.avisar(aviso)


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
    return ""


def _contracargo_a_mano(chargeback_id: str, payment_id: str, problema: str) -> None:
    logger.error("contracargo de mercadopago %s (pago %s): %s", chargeback_id, payment_id, problema)
    cobro.avisar(
        f"Contracargo de Mercado Pago {chargeback_id} (pago {payment_id}): {problema}. "
        "No se revocó nada: revisar a mano en MP.",
    )


#: Margen sobre la vida de la preferencia antes de darla por vencida: da tiempo
#: a que llegue la notificación de un pago hecho sobre el filo.
_MARGEN_VENCIMIENTO = dt.timedelta(minutes=30)

#: Cuánto se guarda la carta de una compra sin cuenta vencida (RF8) por si el
#: pago llega tarde.
_CONSERVAR_CARTA = dt.timedelta(hours=24)

#: Pagos que todavía pueden terminar aprobados: la fila ni se vence ni se descarta.
_ESPERANDO = ("pending", "in_process", "authorized", "in_mediation")


def revisar_vencidas(ahora: dt.datetime) -> dict[str, int]:
    """Cron de RF13: cierra lo que MP nunca nos avisó.

    Una preferencia de MP vencida no notifica (Stripe sí: `checkout.session.expired`),
    y medido en el sandbox MP no reintenta tarde una notificación que tuvo
    respuesta 500. Este barrido, que busca los pagos por `external_reference`,
    es entonces la ÚNICA red de seguridad de una notificación perdida.

    Ruling 12: revisa TODA fila de MP —acreditada o no— todavía sin
    `mp_revisado_at`, pasada la vida de la preferencia más el margen. Cada pago
    aprobado pasa por `procesar_pago`, igual que en el webhook: el de una fila
    sin acreditar la acredita, y uno de más sobre una fila ya acreditada cae en
    `cobro.PagoDuplicado` (reembolso y aviso). Con un pago que todavía puede
    aprobarse la fila queda abierta; si no, se cierra (`mp_revisado_at`) y no
    se vuelve a buscar, así cada aviso definitivo sale una sola vez. Un fallo
    transitorio deja la fila abierta para la corrida siguiente, sin aviso.
    `MPNoConfigurado` corta la corrida.

    Después, en un paso aparte, se descarta la carta de las compras sin cuenta
    cerradas como vencidas hace más de `_CONSERVAR_CARTA` (RF8).
    """
    limite = ahora - stripe_client.VENCIMIENTO_SESION - _MARGEN_VENCIMIENTO
    candidatas = PasarelaCheckout.objects.filter(
        pasarela=PasarelaCheckout.MERCADOPAGO, mp_revisado_at__isnull=True, created_at__lt=limite,
    )
    resumen = {"acreditadas": 0, "vencidas": 0, "esperando": 0, "descartadas": 0}
    for fila in candidatas.order_by("created_at"):
        try:
            _revisar_fila(fila, ahora, resumen)
        except mercadopago_api.MPNoConfigurado:
            logger.error("vencer_checkouts: MP_ACCESS_TOKEN no está configurado: se corta la corrida")
            raise
        except Exception:
            logger.exception("vencer_checkouts: falló la fila %s", fila.checkout_id)
    _descartar_cartas(ahora, resumen)
    logger.info("vencer_checkouts: %s", resumen)
    return resumen


def _revisar_fila(fila: PasarelaCheckout, ahora: dt.datetime, resumen: dict[str, int]) -> None:
    checkout_id = fila.checkout_id
    acreditada_antes = fila.acreditado_at is not None
    try:
        pagos = mercadopago_api.buscar_pagos(checkout_id)
    except mercadopago_api.MPError:
        # Transitorio: queda abierta y se reintenta en 15 minutos, sin aviso.
        logger.exception("vencer_checkouts: no se pudo buscar los pagos de %s", checkout_id)
        return

    aprobados = [p for p in pagos if p.get("status") == "approved"]
    for pago in aprobados:
        try:
            procesar_pago(str(pago.get("id")))
        except cobro.CompraAnonimaSinMail:
            # Definitivo y ya avisado por `cobro`: se cierra para no repetirlo.
            logger.error("vencer_checkouts: el pago %s de %s es de una compra sin mail", pago.get("id"), checkout_id)
        except mercadopago_api.MPNoConfigurado:
            raise
        except Exception:
            logger.exception(
                "vencer_checkouts: no se pudo procesar el pago %s de %s: queda abierta", pago.get("id"), checkout_id,
            )
            return

    fila.refresh_from_db()
    if fila.acreditado_at is not None and not acreditada_antes:
        resumen["acreditadas"] += 1
    if any(p.get("status") in _ESPERANDO for p in pagos):
        resumen["esperando"] += 1
        return

    if not aprobados and PasarelaCheckout.objects.filter(
        pk=fila.pk, acreditado_at__isnull=True, vencido_at__isnull=True,
    ).update(vencido_at=ahora):
        # Sólo sin ningún pago aprobado: uno que no se pudo acreditar (monto,
        # moneda, sin mail) ya se avisó y es plata cobrada, no una fila vencida
        # —ni se lista como tal ni se descarta su carta—.
        resumen["vencidas"] += 1
    PasarelaCheckout.objects.filter(pk=fila.pk, mp_revisado_at__isnull=True).update(mp_revisado_at=ahora)


def _descartar_cartas(ahora: dt.datetime, resumen: dict[str, int]) -> None:
    """RF8: la carta de una compra sin cuenta que el cron cerró como vencida se
    guarda `_CONSERVAR_CARTA` por si el pago llega tarde, y después se borra.
    Ya está confirmado que no hay pago: no se vuelve a preguntar a MP."""
    # Import local: `compra_anonima` importa este módulo.
    from api import compra_anonima

    filas = PasarelaCheckout.objects.filter(
        pasarela=PasarelaCheckout.MERCADOPAGO, anonimo=True, account__isnull=True, sujeto__isnull=False,
        acreditado_at__isnull=True, mp_revisado_at__isnull=False, vencido_at__lt=ahora - _CONSERVAR_CARTA,
    ).values_list("checkout_id", flat=True)
    for checkout_id in filas:
        try:
            descartada = compra_anonima.descartar(checkout_id)
        except Exception:
            logger.exception("vencer_checkouts: no se pudo descartar la carta de %s", checkout_id)
            cobro.avisar(
                f"Mercado Pago {checkout_id}: no se pudo descartar la carta de una compra sin pagar "
                "(la política de privacidad dice que se borra). Revisar a mano.",
            )
            continue
        if descartada:
            resumen["descartadas"] += 1
