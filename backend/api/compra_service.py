"""Qué pasa después de que una compra se acredita, sea cual sea la pasarela.

Existe porque los dos webhooks —Polar, que sigue vivo para los reembolsos de
lo que entró por ahí, y Stripe— tienen que hacer exactamente lo mismo cuando
una compra suelta trae una carta atada, y duplicar cuarenta líneas de lógica de
plata es la forma más segura de que un día se arreglen en un archivo y no en el
otro.

No captura errores a propósito —la única excepción es `SinDerecho` cuando la
unidad comprada saldó una deuda de la cuenta (RF5b), y sólo si el rastro lo
confirma: cualquier otra falta de derecho sube—: cada pasarela decide qué hacer
con un fallo, y la decisión es distinta. Polar deshabilita el endpoint tras diez entregas
fallidas, así que allá se loguea y se responde 2xx; Stripe reintenta tres días
sin castigar el endpoint, así que allá conviene el 5xx.
"""

import logging

from api import catalogo, interpretation_service, mantenimiento
from api.canje import SinDerecho
from api.models import Movimiento, PasarelaCheckout
from interpret.prompts import TIER_LARGO

logger = logging.getLogger(__name__)


def arrancar_informe(cuenta, fila) -> bool:
    """Deja el informe escribiéndose apenas se acredita el pago.

    Devuelve True si quedó un informe escribiéndose (o creado para que lo
    termine el cron, en mantenimiento) y False si no había informe que
    arrancar: quien llama elige con eso el aviso (`informe_en_curso` o
    `compra_acreditada`, spec §11 RF24 v3).

    Es la diferencia entre "pagué y ya se está escribiendo" y "pagué y ahora
    andá a buscar dónde usarlo". Sin esto, `aplicar_compra` consume el derecho
    contra la carta y nadie crea la `Interpretation`: la persona vuelve y
    encuentra el botón de comprar otra vez, con el derecho ya gastado (pasó con
    el primer pago real, el 02-09-2026).

    Sólo para una compra suelta con carta atada. Un pack son cinco informes que
    se usan cuando la persona quiera: elegirle una carta sería gastarle uno sin
    que lo pida.

    `iniciar_generacion` corre en el hilo de la entrega para que la fila quede
    creada antes de responder: si el hilo que sigue muere, es esa fila la que
    `reanudar_informes` encuentra y termina. Es también lo único que la pasarela
    espera —Stripe le da 10 segundos al webhook antes de redirigir a quien
    pagó—, así que la generación se lanza sin bloquear.
    """
    if fila is None or fila.sujeto is None:
        return False

    prod = catalogo.producto(fila.codigo_producto)
    suelto = len(prod.otorga) == 1 and prod.otorga[0][1] == 1
    if not (suelto and prod.capacidades):
        return False

    try:
        interpretacion = interpretation_service.iniciar_generacion(
            fila.sujeto, fila.locale, cuenta, TIER_LARGO,
        )
    except SinDerecho:
        if not (fila.saldo_deuda or _saldo_deuda(cuenta, fila)):
            # Cobré y no entregué por una causa que no entendemos: que suba
            # (el webhook pide reintento y llega a Sentry).
            raise
        # La unidad comprada saldó una deuda de la cuenta y no quedó derecho
        # con qué escribir el informe (RF5b; ver `aplicar_compra`). La compra ya
        # está acreditada: reintentar no lo arregla y un 5xx dejaría el pago en
        # reintento tres días.
        # `error`: cobramos y no hay informe; que Sentry avise. Sin PII.
        logger.error(
            "compra %s de acc=%s acreditada sin derecho para el informe (deuda saldada): "
            "no se escribe", fila.checkout_id, cuenta.pk,
        )
        if not fila.saldo_deuda:
            # Lo normal es que `aplicar_compra` ya la haya marcado; esto cubre
            # un camino que llegue acá sin pasar por el webhook.
            PasarelaCheckout.objects.filter(pk=fila.pk).update(saldo_deuda=True)
            fila.saldo_deuda = True
        return False
    if mantenimiento.activo():
        # Hay un deploy en curso: la fila queda creada —incompleta— y no se
        # lanza el hilo, que moriría con el contenedor viejo a mitad de camino.
        # `reanudar_informes` la termina cuando el mantenimiento pase: es
        # exactamente la red que ese cron ya es.
        logger.info(
            "compra %s acreditada en mantenimiento: el informe queda para el cron",
            fila.checkout_id,
        )
        return True
    interpretation_service.arrancar_en_hilo(interpretacion, cuenta)
    return True


def _saldo_deuda(cuenta, fila) -> bool:
    """¿Se explica la falta de derecho porque la unidad comprada saldó deuda?

    Sin estado propio, por el rastro: hay un otorgamiento de ese producto para
    la cuenta y NADA movió sus derechos después (ni consumo, devolución ni
    revocación). Si sobra un otorgamiento sin saldo y nadie lo gastó, la unidad
    fue a la deuda. Si falta el otorgamiento o algo lo gastó, es otra cosa.

    «Algo» es de ESTE producto: el comprado o lo que otorga (el consumo y la
    devolución quedan con el código otorgado; la revocación, con el
    comprado). Mirando toda la cuenta, una `lectura_breve` gastada en otra
    carta convertía un caso legítimo de deuda en un 5xx de tres días.
    """
    otorgamiento = (
        Movimiento.objects
        .filter(account=cuenta, codigo_producto=fila.codigo_producto, tipo="otorgamiento")
        .order_by("-created_at", "-pk").first()
    )
    if otorgamiento is None:
        return False
    codigos = {fila.codigo_producto} | {
        codigo for codigo, _ in catalogo.producto(fila.codigo_producto).otorga
    }
    return not Movimiento.objects.filter(
        account=cuenta, codigo_producto__in=codigos,
        tipo__in=("consumo", "devolucion", "revocacion"),
        created_at__gte=otorgamiento.created_at,
    ).exists()
