"""Servicio de canje: qué tiene una cuenta y qué puede hacer con eso.

Reemplaza a `ledger.py`. La diferencia de fondo: acá un derecho nombra a su
PRODUCTO, así que un derecho comprado con el pack de 5 informes natales no
puede canjear un producto más caro. Con los dos contadores viejos eso era
imposible de expresar y valía US$345 vendidos por US$150.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from api.catalogo import ACCESO, producto
from api.models import Account, Derecho, Movimiento

logger = logging.getLogger(__name__)


class SinDerecho(Exception):
    """La cuenta no tiene con qué hacer eso. Lleva la capacidad pedida."""

    def __init__(self, capacidad: str):
        self.capacidad = capacidad
        super().__init__(f"sin derecho para {capacidad}")


def otorgar(account, codigo_producto, cantidad, origen, external_id="", note="") -> bool:
    """Da `cantidad` unidades (o vigencia) del producto. Idempotente por external_id.

    Devuelve False si ese external_id ya se había aplicado, sin tocar nada.
    """
    prod = producto(codigo_producto)
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        try:
            with transaction.atomic():
                Movimiento.objects.create(
                    account=acc, codigo_producto=codigo_producto, tipo="otorgamiento",
                    cantidad=cantidad, origen=origen, external_id=external_id, note=note,
                )
        except IntegrityError:
            if external_id and Movimiento.objects.filter(external_id=external_id).exists():
                logger.info("otorgamiento duplicado ignorado (external_id=%s)", external_id)
                return False
            raise

        if prod.naturaleza == ACCESO:
            # El default de creación ya tiene que traer vigente_hasta puesta:
            # el CheckConstraint exige exactamente una de las dos columnas no
            # nula, y un derecho recién creado con cantidad_restante=None y
            # vigente_hasta=None (sin default) lo viola.
            vigencia_nueva = timezone.now() + timezone.timedelta(days=prod.duracion_dias)
            derecho, created = Derecho.objects.get_or_create(
                account=acc, codigo_producto=codigo_producto,
                defaults={"cantidad_restante": None, "vigente_hasta": vigencia_nueva},
            )
            if not created:
                desde = max(derecho.vigente_hasta or timezone.now(), timezone.now())
                derecho.vigente_hasta = desde + timezone.timedelta(days=prod.duracion_dias)
                derecho.save(update_fields=["vigente_hasta", "updated_at"])
        else:
            derecho, _ = Derecho.objects.get_or_create(
                account=acc, codigo_producto=codigo_producto,
                defaults={"cantidad_restante": 0},
            )
            # La deuda se cancela antes de dar saldo: quien reembolsó algo que
            # ya usó y vuelve a comprar, primero salda lo que debe.
            aplicado_a_deuda = min(acc.deuda, cantidad)
            if aplicado_a_deuda:
                acc.deuda -= aplicado_a_deuda
                acc.save(update_fields=["deuda"])
                account.deuda = acc.deuda
            derecho.cantidad_restante += cantidad - aplicado_a_deuda
            derecho.save(update_fields=["cantidad_restante", "updated_at"])
    return True
