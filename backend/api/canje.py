"""Servicio de canje: qué tiene una cuenta y qué puede hacer con eso.

Reemplaza a `ledger.py`. La diferencia de fondo: acá un derecho nombra a su
PRODUCTO, así que un derecho comprado con el pack de 5 informes natales no
puede canjear un producto más caro. Con los dos contadores viejos eso era
imposible de expresar y valía US$345 vendidos por US$150.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from api.catalogo import ACCESO, producto, productos_con_capacidad
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
    # El derecho se otorga en el producto de destino, no en el que se compró:
    # el pack de 5 informes natales (otorga=("informe_natal", 5)) tiene que
    # dejar un derecho de informe_natal, no uno de pack_5_natal que nadie
    # consulta. El Movimiento sí guarda el producto comprado: es el rastro
    # de auditoría de lo que entró por Polar.
    codigo_otorgado, multiplicador = prod.otorga
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
                account=acc, codigo_producto=codigo_otorgado,
                defaults={"cantidad_restante": None, "vigente_hasta": vigencia_nueva},
            )
            if not created:
                desde = max(derecho.vigente_hasta or timezone.now(), timezone.now())
                derecho.vigente_hasta = desde + timezone.timedelta(days=prod.duracion_dias)
                derecho.save(update_fields=["vigente_hasta", "updated_at"])
        else:
            derecho, _ = Derecho.objects.get_or_create(
                account=acc, codigo_producto=codigo_otorgado,
                defaults={"cantidad_restante": 0},
            )
            otorgado = cantidad * multiplicador
            # La deuda se cancela antes de dar saldo: quien reembolsó algo que
            # ya usó y vuelve a comprar, primero salda lo que debe.
            aplicado_a_deuda = min(acc.deuda, otorgado)
            if aplicado_a_deuda:
                acc.deuda -= aplicado_a_deuda
                acc.save(update_fields=["deuda"])
                account.deuda = acc.deuda
            derecho.cantidad_restante += otorgado - aplicado_a_deuda
            derecho.save(update_fields=["cantidad_restante", "updated_at"])
    return True


def canjear(account, capacidad: str, chart, build=None):
    """Consume una unidad de la capacidad y la vincula a esa carta.

    Si la carta ya tiene canjeada esa capacidad, es un no-op: NO se consume
    nada y el derecho queda disponible. El mismo camino lo recorre alguien que
    pagó por una carta ya ampliada (dos pestañas, o usó el pack mientras el
    checkout estaba abierto), y cobrar sin entregar es el único error que
    una superficie de plata no puede cometer.

    `build`, si se pasa, corre dentro de la misma transacción que el
    descuento: lo que construya queda atado al mismo commit que el
    `Movimiento`, así nunca se cobra sin dejar el objeto construido.
    """
    codigos = {p.otorga[0] for p in productos_con_capacidad(capacidad)}
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)

        ya = Movimiento.objects.filter(
            account=acc, chart=chart, tipo="consumo", codigo_producto__in=codigos,
        ).first()
        if ya is not None:
            return None, ya.codigo_producto

        derecho = (
            Derecho.objects.filter(
                account=acc, codigo_producto__in=codigos, cantidad_restante__gt=0,
            )
            .order_by("codigo_producto")
            .first()
        )
        if derecho is None:
            raise SinDerecho(capacidad)

        derecho.cantidad_restante -= 1
        derecho.save(update_fields=["cantidad_restante", "updated_at"])
        construido = build() if build is not None else None
        Movimiento.objects.create(
            account=acc, codigo_producto=derecho.codigo_producto, tipo="consumo",
            cantidad=-1, origen="compra", chart=chart,
        )
    return construido, derecho.codigo_producto


def devolver(account, codigo_producto, external_id, chart=None, note="") -> bool:
    """Repone un derecho cuya entrega falló. Idempotente por external_id.

    Desvincula el movimiento de consumo de esa carta (no lo borra: `Movimiento`
    es un registro append-only) para que vuelva a estar libre: si el vínculo
    quedara, el no-op de `canjear` la daría por entregada para siempre y el
    usuario no podría regenerar el informe pese a tener el derecho repuesto.
    """
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        try:
            with transaction.atomic():
                Movimiento.objects.create(
                    account=acc, codigo_producto=codigo_producto, tipo="devolucion",
                    cantidad=1, origen="ajuste", chart=chart,
                    external_id=external_id, note=note,
                )
        except IntegrityError:
            if Movimiento.objects.filter(external_id=external_id).exists():
                logger.info("devolución duplicada ignorada (external_id=%s)", external_id)
                return False
            raise

        if chart is not None:
            Movimiento.objects.filter(
                account=acc, chart=chart, tipo="consumo", codigo_producto=codigo_producto,
            ).update(chart=None)

        derecho, _ = Derecho.objects.get_or_create(
            account=acc, codigo_producto=codigo_producto, defaults={"cantidad_restante": 0},
        )
        derecho.cantidad_restante += 1
        derecho.save(update_fields=["cantidad_restante", "updated_at"])
    return True


def puede(account, capacidad: str) -> bool:
    """¿La cuenta puede hacer esto?

    Es la única pregunta que hacen las vistas y las pantallas. Preguntar por
    producto obligaría a recorrerlas todas cada vez que se agrega un plan.
    """
    codigos = {p.otorga[0] for p in productos_con_capacidad(capacidad)}
    if not codigos:
        return False
    ahora = timezone.now()
    for derecho in Derecho.objects.filter(account=account, codigo_producto__in=codigos):
        if derecho.cantidad_restante is not None and derecho.cantidad_restante > 0:
            return True
        if derecho.vigente_hasta is not None and derecho.vigente_hasta > ahora:
            return True
    return False


def derechos_de(account) -> list[dict]:
    """Lo que la cuenta tiene, tal como lo necesita `/api/account/`."""
    return [
        {
            "codigo_producto": d.codigo_producto,
            "cantidad_restante": d.cantidad_restante,
            "vigente_hasta": d.vigente_hasta,
        }
        for d in Derecho.objects.filter(account=account).order_by("codigo_producto")
    ]
