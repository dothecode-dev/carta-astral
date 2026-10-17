"""Conteo propio por día, sin cookies ni datos personales (`ConteoDiario`).

Es el denominador real del embudo: PostHog sólo ve a quien acepta las
cookies. Contar nunca puede romper lo que cuenta: si la base falla, se loguea
y se sigue, y el fallo queda en su propio savepoint para no envenenar la
transacción de quien llamó.
"""

import datetime
import logging

from django.db import DatabaseError, transaction
from django.db.models import F
from django.utils import timezone

from api.models import ConteoDiario, PasarelaCheckout

logger = logging.getLogger(__name__)

EVENTOS = tuple(clave for clave, _ in ConteoDiario.EVENTOS)


def contar(evento: str) -> None:
    """Suma uno al contador de hoy (UTC) para `evento`."""
    if evento not in EVENTOS:
        logger.error("conteo: evento desconocido %r", evento)
        return
    try:
        with transaction.atomic():
            fila, _ = ConteoDiario.objects.get_or_create(fecha=timezone.now().date(), evento=evento)
            # UPDATE ... SET cantidad = cantidad + 1: atómico entre procesos.
            ConteoDiario.objects.filter(pk=fila.pk).update(cantidad=F("cantidad") + 1)
    except DatabaseError:
        logger.exception("conteo: no se pudo contar %s", evento)


def resumen(dias: int = 7) -> dict:
    """Los últimos `dias` días (hoy incluido, UTC): por día y en total.

    `compra_pagada` sale de los pagos acreditados (`PasarelaCheckout`), no de
    un contador: ya está en la base. Un canje con cupón del 100 % no es pago.
    """
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(dias)]
    claves = (*EVENTOS, "compra_pagada")
    por_dia = {str(f): dict.fromkeys(claves, 0) for f in fechas}
    for fila in ConteoDiario.objects.filter(fecha__gte=fechas[-1]):
        por_dia[str(fila.fecha)][fila.evento] = fila.cantidad
    pagas = PasarelaCheckout.objects.filter(
        acreditado_at__date__gte=fechas[-1],
    ).exclude(checkout_id__startswith="cupon_")
    for acreditado in pagas.values_list("acreditado_at", flat=True):
        por_dia[str(acreditado.date())]["compra_pagada"] += 1
    total = {c: sum(d[c] for d in por_dia.values()) for c in claves}
    return {"dias": dias, "total": total, "por_dia": por_dia}
