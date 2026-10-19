"""Chequeo de arranque (RF6): todo producto a la venta tiene su Product en
`STRIPE_PRODUCTOS`. Warning y no Error: el sitio arranca igual (la lectura
breve y las cartas no cobran), pero el checkout de ese producto va a
responder 503 y conviene enterarse antes que el primer comprador.

Los Warnings se devuelven siempre (salen por stderr en cualquier comando de
`manage.py`). El aviso por Telegram sólo sale si `AVISAR_CHECKS=1`, que pone
únicamente el entrypoint: Django corre los checks en casi todos los comandos,
incluido `reanudar_informes` cada 2 minutos, y avisar en cada uno sería spam."""

import os

from django.conf import settings
from django.core.checks import Tags, Warning, register

from api import avisos
from api.catalogo import a_la_venta


@register(Tags.compatibility, "stripe")
def productos_en_stripe(app_configs, **kwargs):
    encontrados = []
    mapeo = settings.STRIPE_PRODUCTOS
    vacios = sorted(c for c, v in mapeo.items() if not v)
    faltan = [p.codigo for p in a_la_venta() if p.codigo not in mapeo]
    if faltan:
        encontrados.append(Warning(
            f"productos a la venta sin Product en STRIPE_PRODUCTOS: {', '.join(faltan)}",
            hint="el checkout de esos productos responde 503 hasta mapearlos", id="api.W001",
        ))
    if vacios:
        encontrados.append(Warning(
            f"productos con Product vacío en STRIPE_PRODUCTOS: {', '.join(vacios)}",
            hint="un Product vacío no identifica nada; mapealo al prod_… real", id="api.W001",
        ))
    valores = [v for v in mapeo.values() if v]
    repetidos = {v for v in valores if valores.count(v) > 1}
    if repetidos:
        encontrados.append(Warning(
            f"un mismo Product para más de un código: {', '.join(sorted(repetidos))}",
            hint="el webhook no podría saber qué se compró", id="api.W002",
        ))
    if os.environ.get("AVISAR_CHECKS") == "1":
        for aviso in encontrados:
            avisos.avisar_admin(f"Arranque del backend: {aviso.msg}")
    return encontrados


@register(Tags.compatibility, "mercadopago")
def mercadopago_configurado(app_configs, **kwargs):
    """RF15: con el cobro en pesos prendido, Mercado Pago necesita su token, el
    secreto del webhook y las dos URL (https). Con el flag apagado, nada. Sólo
    se nombra la variable, nunca su valor. Mismo aviso por Telegram que Stripe."""
    if not settings.COBRO_ARS_ENABLED:
        return []
    encontrados = []
    for nombre in ("MP_ACCESS_TOKEN", "MP_WEBHOOK_SECRET", "MP_NOTIFICACION_URL", "MP_RETORNO_URL"):
        if not getattr(settings, nombre, ""):
            encontrados.append(Warning(
                f"COBRO_ARS_ENABLED está prendido y falta {nombre}",
                hint="el checkout en pesos no puede funcionar sin esa variable", id="api.W003",
            ))
    for nombre in ("MP_NOTIFICACION_URL", "MP_RETORNO_URL"):
        valor = getattr(settings, nombre, "")
        if valor and not valor.startswith("https://"):
            encontrados.append(Warning(
                f"{nombre} no es https://",
                hint="Mercado Pago exige https para notificar y volver", id="api.W004",
            ))
    if os.environ.get("AVISAR_CHECKS") == "1":
        for aviso in encontrados:
            avisos.avisar_admin(f"Arranque del backend: {aviso.msg}")
    return encontrados
