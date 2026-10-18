"""Cuánto se le devolvió a una compra y cuántas unidades se le revocaron.

Lo usan el reembolso (`webhooks_stripe._reembolsar`) y la disputa
(`disputas`). Las unidades revocadas se GUARDAN en la compra
(`unidades_revocadas`) en vez de deducirse del monto devuelto: cada reembolso
parcial redondea hacia arriba por su cuenta (no existe medio informe), así que
la suma de varios parciales no es el redondeo de la suma, y deducirlo revocaba
más de lo que el pack había dado (revisión del 18-10-2026).

Una «unidad» es una de lo que el producto otorga: un pack de 5 tiene 5. Un
combo (otorga más de una cosa) cuenta como una sola, porque no se revoca a
medias.

Quien llama tiene la compra bloqueada (`select_for_update`): estas cuentas
leen `unidades_revocadas` y la actualizan.
"""

from django.db import models

from api import catalogo
from api.canje import revocar
from api.models import Disputa, PasarelaCheckout


def unidades_de(fila) -> tuple[str, int]:
    """`(codigo, total)`: qué se revoca por unidad y cuántas dio la compra."""
    prod = catalogo.producto(fila.codigo_producto)
    if len(prod.otorga) == 1:
        codigo, multiplicador = prod.otorga[0]
        return codigo, multiplicador
    return fila.codigo_producto, 1


def pagado(fila) -> int:
    return fila.precio_de_lista() - fila.descuento_centavos


def quedan(fila) -> int:
    """Unidades de la compra que todavía no se revocaron."""
    _codigo, total = unidades_de(fila)
    return max(0, total - fila.unidades_revocadas)


def cubre_todo(fila, monto: int) -> bool:
    """Si con este reembolso queda devuelto todo lo pagado, contando los
    reembolsos anteriores: dos mitades de un combo lo devuelven entero aunque
    ninguna sola alcance. Lo que anotó una disputa abierta NO cuenta: es
    plata que Stripe puede devolver, y contarla hacía que un reembolso
    parcial tomara de la disputa todas sus unidades. Lo pagado en 0 (regalo
    del 100 %) es siempre todo."""
    base = pagado(fila)
    if base <= 0:
        return True
    de_disputas = (
        Disputa.objects.filter(fila=fila, estado=Disputa.ABIERTA)
        .aggregate(total=models.Sum("monto_anotado"))["total"] or 0
    )
    return fila.reembolsado_centavos - de_disputas + monto >= base


def unidades_pedidas(fila, monto: int) -> int:
    """Cuántas unidades cubre un reembolso de `monto`, sin mirar cuántas
    quedan: redondeando hacia arriba (decidido el 03-09-2026: ante la duda no
    se regala producto), y todas si con él queda devuelto todo lo pagado."""
    _codigo, total = unidades_de(fila)
    base = pagado(fila)
    if cubre_todo(fila, monto):
        return total
    return min(total, -(-monto * total // base))


def revocar_unidades(fila, unidades: int, external_id: str) -> tuple[str, int, bool] | None:
    """Revoca `unidades` de la compra. Devuelve `(codigo, cantidad, entera)`
    tal como se le pasó a `canje.revocar` —para poder reponer exactamente
    eso—, o None si `revocar` ya lo había aplicado (mismo `external_id`).

    Si son todas y no se había revocado ninguna, se revoca el PRODUCTO
    comprado: el Movimiento dice qué se compró y `revocar` lo traduce."""
    codigo, total = unidades_de(fila)
    entera = fila.unidades_revocadas == 0 and unidades == total
    if entera:
        codigo, cantidad = fila.codigo_producto, 1
    else:
        cantidad = unidades
    if not revocar(fila.account, codigo, cantidad, external_id=external_id):
        return None
    return codigo, cantidad, entera


def registrar(fila, unidades: int, monto: int) -> None:
    """Suma (o resta, con negativos) lo revocado y lo devuelto a la compra."""
    PasarelaCheckout.objects.filter(pk=fila.pk).update(
        unidades_revocadas=models.F("unidades_revocadas") + unidades,
        reembolsado_centavos=models.F("reembolsado_centavos") + monto,
    )
    fila.refresh_from_db(fields=["unidades_revocadas", "reembolsado_centavos"])
