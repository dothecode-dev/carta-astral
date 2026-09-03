"""Qué pasa después de que una compra se acredita, sea cual sea la pasarela.

Existe porque los dos webhooks —Polar, que sigue vivo para los reembolsos de
lo que entró por ahí, y Stripe— tienen que hacer exactamente lo mismo cuando
una compra suelta trae una carta atada, y duplicar cuarenta líneas de lógica de
plata es la forma más segura de que un día se arreglen en un archivo y no en el
otro.

No captura errores a propósito: cada pasarela decide qué hacer con un fallo, y
la decisión es distinta. Polar deshabilita el endpoint tras diez entregas
fallidas, así que allá se loguea y se responde 2xx; Stripe reintenta tres días
sin castigar el endpoint, así que allá conviene el 5xx.
"""

import logging

from api import catalogo, interpretation_service, mantenimiento
from interpret.prompts import TIER_LARGO

logger = logging.getLogger(__name__)


def arrancar_informe(cuenta, fila) -> None:
    """Deja el informe escribiéndose apenas se acredita el pago.

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
    if fila is None or fila.chart is None:
        return

    prod = catalogo.producto(fila.codigo_producto)
    suelto = len(prod.otorga) == 1 and prod.otorga[0][1] == 1
    if not (suelto and prod.capacidades):
        return

    interpretacion = interpretation_service.iniciar_generacion(
        fila.chart, fila.locale, cuenta, TIER_LARGO,
    )
    if mantenimiento.activo():
        # Hay un deploy en curso: la fila queda creada —incompleta— y no se
        # lanza el hilo, que moriría con el contenedor viejo a mitad de camino.
        # `reanudar_informes` la termina cuando el mantenimiento pase: es
        # exactamente la red que ese cron ya es.
        logger.info(
            "compra %s acreditada en mantenimiento: el informe queda para el cron",
            fila.checkout_id,
        )
        return
    interpretation_service.arrancar_en_hilo(interpretacion, fila.chart, cuenta)
