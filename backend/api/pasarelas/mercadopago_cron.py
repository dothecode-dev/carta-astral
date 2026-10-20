"""Mercado Pago en pesos: el cron de `vencer_checkouts` (RF13): cierra lo que
MP nunca avisó y concilia los pagos que cambiaron."""

import datetime as dt
import logging

from django.core.cache import cache

from api import cobro, compra_anonima, reglas_checkout
from api.models import PasarelaCheckout
from api.pasarelas import mercadopago_api
from api.pasarelas.mercadopago_pagos import _REFERENCIA_NUESTRA, FilaInexistente, procesar_pago

logger = logging.getLogger(__name__)

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
    limite = ahora - reglas_checkout.VENCIMIENTO_SESION - _MARGEN_VENCIMIENTO
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
    # En una fila acreditada sólo se buscan OTROS pagos: los duplicados. Con
    # el informe ya arrancado, reprocesar el que la acreditó no haría nada
    # (`cobro.acreditar` lo corta por `informe_arrancado_at`); sin arrancar,
    # reintentaría un arranque que ya falló dos veces y, si sigue fallando,
    # dejaría la fila abierta para siempre. Ese caso ya se avisó y se
    # resuelve a mano con `acreditar_pago`.
    por_procesar = [
        p for p in aprobados if not (acreditada_antes and str(p.get("id")) == fila.pago_id)
    ]
    for pago in por_procesar:
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


#: Ventana de la conciliación: el cron corre cada 15 minutos, así que cada
#: pago actualizado se ve en varias corridas (solapada a propósito: una corrida
#: caída no deja huecos).
_VENTANA_CONCILIACION = dt.timedelta(hours=2)

#: Cuánto se recuerda que una versión de un pago ya se concilió: más que la
#: ventana, para que ninguna corrida la vuelva a procesar.
_RECORDAR_CONCILIADO = 24 * 60 * 60


def conciliar_actualizados(ahora: dt.datetime) -> dict[str, int]:
    """Ruling 15: pasa por `procesar_pago` los pagos nuestros que MP modificó
    en la ventana reciente, por si se perdió su notificación.

    `revisar_vencidas` mira cada fila una sola vez, al vencer la preferencia;
    un reembolso, un reembolso parcial o un cambio de estado posteriores sólo
    llegan por el webhook, y MP no reintenta tarde (medido en sandbox). Esto
    los recupera. `procesar_pago` es idempotente: un pago ya acreditado con su
    informe arrancado no toca nada (`cobro.acreditar`), y un reembolso ya
    aplicado tiene su constancia.

    Cada versión de un pago (id + `date_last_updated`) se procesa una sola
    vez: la ventana se solapa y sin esto lo que sólo avisa (mediación,
    contracargo) avisaría en cada corrida. Una que falla se reintenta en la
    corrida siguiente, sólo con log: el aviso de una red que se repite cada 15
    minutos sería ruido. `MPNoConfigurado` corta la corrida.
    """
    resumen = {"conciliados": 0, "fallidos": 0}
    try:
        pagos = mercadopago_api.buscar_pagos_actualizados(ahora - _VENTANA_CONCILIACION, ahora)
    except mercadopago_api.MPError:
        logger.exception("vencer_checkouts: no se pudo buscar los pagos actualizados")
        return resumen
    for pago in pagos:
        referencia = pago.get("external_reference")
        pago_id = str(pago.get("id") or "")
        if not pago_id or not isinstance(referencia, str) or not _REFERENCIA_NUESTRA.fullmatch(referencia):
            continue
        clave = f"mp:conciliado:{pago_id}:{pago.get('date_last_updated') or ''}"
        if cache.get(clave):
            continue
        try:
            procesar_pago(pago_id)
        except mercadopago_api.MPNoConfigurado:
            raise
        except (FilaInexistente, cobro.CompraAnonimaSinMail):
            # Definitivos y ya avisados: no se repiten cada 15 minutos.
            logger.error("vencer_checkouts: el pago %s (%s) no se pudo conciliar", pago_id, referencia)
            resumen["fallidos"] += 1
        except Exception:
            logger.exception("vencer_checkouts: falló la conciliación del pago %s (%s)", pago_id, referencia)
            resumen["fallidos"] += 1
            continue
        else:
            resumen["conciliados"] += 1
        cache.set(clave, True, _RECORDAR_CONCILIADO)
    logger.info("vencer_checkouts: conciliación %s", resumen)
    return resumen


def _descartar_cartas(ahora: dt.datetime, resumen: dict[str, int]) -> None:
    """RF8: la carta de una compra sin cuenta que el cron cerró como vencida se
    guarda `_CONSERVAR_CARTA` por si el pago llega tarde, y después se borra.
    Ya está confirmado que no hay pago: no se vuelve a preguntar a MP."""
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
