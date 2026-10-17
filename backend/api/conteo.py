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
    hoy = timezone.now().date()
    try:
        with transaction.atomic():
            # Lo común es que la fila del día ya exista: un solo UPDATE
            # (cantidad = cantidad + 1, atómico entre procesos). Sólo el primer
            # conteo del día la crea; si dos la crean a la vez, `get_or_create`
            # resuelve el choque y el UPDATE de abajo suma igual.
            if not ConteoDiario.objects.filter(fecha=hoy, evento=evento).update(cantidad=F("cantidad") + 1):
                fila, _ = ConteoDiario.objects.get_or_create(fecha=hoy, evento=evento)
                ConteoDiario.objects.filter(pk=fila.pk).update(cantidad=F("cantidad") + 1)
    except DatabaseError:
        logger.exception("conteo: no se pudo contar %s", evento)


def resumen(dias: int = 7) -> dict:
    """Los últimos `dias` días COMPLETOS (UTC), por día y en total, y hoy aparte.

    Hoy va separado porque el informe sale a la mañana: con unas horas, sumarlo
    o ponerlo en fila con días enteros se lee como una caída.

    `compra_pagada` sale de los pagos acreditados (`PasarelaCheckout`), no de
    un contador: ya está en la base. No cuentan los canjes con cupón del 100 %
    ni las compras reembolsadas. Los contadores cuentan VECES, no personas.
    """
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(1, dias + 1)]
    claves = (*EVENTOS, "compra_pagada")
    por_dia = {str(f): dict.fromkeys(claves, 0) for f in (hoy, *fechas)}
    for fila in ConteoDiario.objects.filter(fecha__gte=fechas[-1]):
        por_dia[str(fila.fecha)][fila.evento] = fila.cantidad
    pagas = PasarelaCheckout.objects.filter(
        acreditado_at__date__gte=fechas[-1], reembolsado_centavos=0,
    ).exclude(checkout_id__startswith="cupon_")
    for acreditado in pagas.values_list("acreditado_at", flat=True):
        dia = str(acreditado.date())
        if dia in por_dia:
            por_dia[dia]["compra_pagada"] += 1
    hoy_parcial = por_dia.pop(str(hoy))
    total = {c: sum(d[c] for d in por_dia.values()) for c in claves}
    return {"dias": dias, "total": total, "hoy": hoy_parcial, "por_dia": por_dia}


def serie(dias: int = 90) -> dict:
    """La historia diaria para el gráfico, del día más viejo a hoy (incluido).

    Una lista por evento, alineada con `fechas`, con 0 donde no hubo nada.
    `compra_pagada` con el mismo criterio que `resumen`.
    """
    hoy = timezone.now().date()
    fechas = [hoy - datetime.timedelta(days=i) for i in range(dias - 1, -1, -1)]
    indice = {f: i for i, f in enumerate(fechas)}
    claves = (*EVENTOS, "compra_pagada")
    valores = {c: [0] * dias for c in claves}
    for fila in ConteoDiario.objects.filter(fecha__gte=fechas[0]):
        valores[fila.evento][indice[fila.fecha]] = fila.cantidad
    pagas = PasarelaCheckout.objects.filter(
        acreditado_at__date__gte=fechas[0], reembolsado_centavos=0,
    ).exclude(checkout_id__startswith="cupon_")
    for acreditado in pagas.values_list("acreditado_at", flat=True):
        if (i := indice.get(acreditado.date())) is not None:
            valores["compra_pagada"][i] += 1
    return {"fechas": [str(f) for f in fechas], **valores}
