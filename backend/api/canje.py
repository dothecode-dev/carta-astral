"""Servicio de canje: qué tiene una cuenta y qué puede hacer con eso.

Reemplaza a `ledger.py`. La diferencia de fondo: acá un derecho nombra a su
PRODUCTO, así que un derecho comprado con el pack de 5 informes natales no
puede canjear un producto más caro. Con los dos contadores viejos eso era
imposible de expresar y valía US$345 vendidos por US$150.
"""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from api.catalogo import ACCESO, codigos_otorgados_por, producto
from api.models import Account, Chart, Derecho, Movimiento

logger = logging.getLogger(__name__)


class SinDerecho(Exception):
    """La cuenta no tiene con qué hacer eso. Lleva la capacidad pedida."""

    def __init__(self, capacidad: str):
        self.capacidad = capacidad
        super().__init__(f"sin derecho para {capacidad}")


class MontoInvalido(Exception):
    """El monto pagado no coincide con el precio del catálogo."""


def _movimiento_idempotente(**campos) -> bool:
    """Crea el `Movimiento`; devuelve False si ese `external_id` ya estaba aplicado.

    El savepoint anidado es lo que permite que el `IntegrityError` de un
    duplicado no envenene la transacción externa cuando esto corre dentro de
    otra (el `select_for_update` de quien llama). Cualquier `IntegrityError`
    que no sea ese duplicado se relanza: no es un caso que este helper sepa
    resolver.
    """
    external_id = campos.get("external_id", "")
    try:
        with transaction.atomic():
            Movimiento.objects.create(**campos)
    except IntegrityError:
        if external_id and Movimiento.objects.filter(external_id=external_id).exists():
            return False
        raise
    return True


def otorgar(account, codigo_producto, cantidad, origen, external_id="", note="") -> bool:
    """Da `cantidad` unidades (o vigencia) del producto. Idempotente por external_id.

    Devuelve False si ese external_id ya se había aplicado, sin tocar nada.
    """
    prod = producto(codigo_producto)
    # El derecho se otorga en el producto de destino, no en el que se compró:
    # el pack de 5 informes natales (otorga=(("informe_natal", 5),)) tiene que
    # dejar un derecho de informe_natal, no uno de pack_5_natal que nadie
    # consulta. El Movimiento sí guarda el producto comprado: es el rastro
    # de auditoría de lo que entró por Polar.
    #
    # Se recorre porque un producto puede otorgar MÁS DE UNA cosa: un combo
    # "carta + horóscopo" deja un derecho de cada uno. Un pack sigue siendo el
    # caso de un solo par con cantidad > 1.
    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        if not _movimiento_idempotente(
            account=acc, codigo_producto=codigo_producto, tipo="otorgamiento",
            cantidad=cantidad, origen=origen, external_id=external_id, note=note,
        ):
            logger.info("otorgamiento duplicado ignorado (external_id=%s)", external_id)
            return False

        for codigo_otorgado, multiplicador in prod.otorga:
            _aplicar_otorgamiento(acc, account, prod, codigo_otorgado, cantidad * multiplicador)
    return True


def _aplicar_otorgamiento(acc, account, prod, codigo_otorgado: str, otorgado: int) -> None:
    """Deja UN derecho concreto, ya traducido y multiplicado.

    Lo llama `otorgar` una vez por cada cosa que el producto otorgue: una sola
    para un producto suelto o un pack, varias para un combo. Corre siempre
    dentro de la transacción y del `select_for_update` de `otorgar`.
    """
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
        return

    derecho, _ = Derecho.objects.get_or_create(
        account=acc, codigo_producto=codigo_otorgado, defaults={"cantidad_restante": 0},
    )
    # La deuda se cancela antes de dar saldo: quien reembolsó algo que ya usó
    # y vuelve a comprar, primero salda lo que debe.
    aplicado_a_deuda = min(acc.deuda, otorgado)
    if aplicado_a_deuda:
        acc.deuda -= aplicado_a_deuda
        acc.save(update_fields=["deuda"])
        account.deuda = acc.deuda
    derecho.cantidad_restante += otorgado - aplicado_a_deuda
    derecho.save(update_fields=["cantidad_restante", "updated_at"])


def aplicar_compra(
    account, codigo_producto, monto_centavos, external_id,
    chart=None, chart_id=None, descuento_centavos=0,
) -> bool:
    """Traduce un pago a derechos, con lo que el producto declara en el catálogo.

    Quien llama no sabe cuántas unidades da cada producto: eso lo dice el
    catálogo, y así agregar un pack es una línea allá y ninguna acá.
    """
    prod = producto(codigo_producto)
    if not (0 <= descuento_centavos <= prod.precio_centavos):
        # Sin esta cota, un descuento inventado en el payload hace pasar
        # cualquier monto (incluido 0 o negativo) como si el catálogo lo
        # avalara: el descuento tiene que achicar el precio, nunca invertirlo.
        logger.error(
            "descuento fuera de rango: producto=%s precio=%s descuento=%s external_id=%s",
            codigo_producto, prod.precio_centavos, descuento_centavos, external_id,
        )
        raise MontoInvalido(codigo_producto)

    esperado = prod.precio_centavos - descuento_centavos
    if monto_centavos != esperado:
        # Hay dos fuentes de precio —este catálogo y el de Polar—: si divergen,
        # todos los pagos de este producto se rechazan. Sin este error a la
        # vista, es caja cerrada en silencio.
        logger.error(
            "monto no coincide con el catálogo: producto=%s esperado=%s recibido=%s external_id=%s",
            codigo_producto, esperado, monto_centavos, external_id,
        )
        raise MontoInvalido(codigo_producto)

    # Otorgamiento y canje son UN solo átomo. El webhook de la pasarela
    # responde 5xx ante un fallo transitorio para que Stripe reintente durante
    # tres días; sin este átomo, un canje que falla después de un otorgamiento
    # ya committeado deja el `external_id` aplicado, y cada reintento sale por
    # el `return False` del duplicado sin llegar nunca al canje: el comprador
    # se queda con el derecho puesto y sin informe, para siempre. O las dos
    # cosas, o ninguna.
    #
    # Los `atomic` de `otorgar`, `canjear` y `_movimiento_idempotente` pasan a
    # ser savepoints anidados. Eso es exactamente para lo que existen: el
    # `IntegrityError` del duplicado revierte su savepoint y no envenena este
    # átomo. No sacarlos.
    with transaction.atomic():
        # Se otorga el producto COMPRADO, no el que ese producto otorga:
        # `otorgar` ya traduce por `Producto.otorga` (Task 3), y así el
        # Movimiento guarda `pack_5_natal` —qué se pagó— mientras el Derecho
        # queda en informe_natal.
        if not otorgar(
            account, codigo_producto, 1, origen="compra",
            external_id=external_id, note=f"compra:{codigo_producto}",
        ):
            return False

        carta = chart
        if carta is None and chart_id is not None:
            carta = Chart.objects.filter(pk=chart_id).first()
        # Sólo canjea una compra suelta: un producto que otorga más de una
        # unidad es un pack, y uno que otorga más de un producto es un combo —
        # ninguno de los dos canjea al comprar, porque no hay una sola cosa que
        # canjear, aunque el llamador le pase una carta. Si la carta ya no
        # existe, el otorgamiento ya ocurrió y el canje se omite igual.
        suelto = len(prod.otorga) == 1 and prod.otorga[0][1] == 1
        if carta is not None and suelto and prod.capacidades:
            canjear(account, prod.capacidades[0], carta)
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
    codigos = codigos_otorgados_por(capacidad)
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
        if not _movimiento_idempotente(
            account=acc, codigo_producto=codigo_producto, tipo="devolucion",
            cantidad=1, origen="ajuste", chart=chart, external_id=external_id, note=note,
        ):
            logger.info("devolución duplicada ignorada (external_id=%s)", external_id)
            return False

        derecho = Derecho.objects.filter(account=acc, codigo_producto=codigo_producto).first()
        if derecho is None:
            # Para haberse consumido, el derecho tuvo que existir (queda en 0,
            # no desaparece). Si no existe, no lo acuñamos de la nada: un
            # codigo_producto equivocado del llamador inflaría saldo en
            # silencio. El Movimiento de devolución ya quedó creado arriba:
            # es el rastro de auditoría del intento.
            logger.error(
                "devolver sin derecho previo (account=%s, codigo_producto=%s, external_id=%s)",
                acc.pk, codigo_producto, external_id,
            )
            return False

        if chart is not None:
            Movimiento.objects.filter(
                account=acc, chart=chart, tipo="consumo", codigo_producto=codigo_producto,
            ).update(chart=None)
        else:
            # Rastro para diagnosticar una carta que quedó bloqueada porque
            # quien llamó a `devolver` se olvidó de pasar la carta.
            logger.debug(
                "devolver sin carta (account=%s, codigo_producto=%s, external_id=%s): "
                "no se desvinculó ningún movimiento de consumo",
                acc.pk, codigo_producto, external_id,
            )

        derecho.cantidad_restante += 1
        derecho.save(update_fields=["cantidad_restante", "updated_at"])
    return True


def revocar(account, codigo_producto, cantidad, external_id, note="") -> bool:
    """Reembolso: revoca primero lo que no se canjeó; lo que excede queda como deuda.

    Nunca se le saca a nadie una interpretación ya entregada: si el derecho no
    alcanza para cubrir el reembolso, la diferencia se anota como deuda de la
    cuenta en vez de tocar el `Derecho` (que no puede bajar de 0) o el
    `Movimiento` de consumo que dejó la lectura. Si la cuenta reincide y cruza
    `REFUND_FLAG_THRESHOLD`, queda `flagged` para revisión manual. Idempotente
    por external_id, como `otorgar` y `devolver`.
    """
    if account is None:
        # Chargeback contra una cuenta ya borrada (spec RF22): llega meses
        # después del borrado y no hay a quién cobrarle la deuda ni bajarle
        # el derecho, pero el movimiento se registra igual para que la
        # contabilidad cierre y no reviente el webhook.
        if not _movimiento_idempotente(
            account=None, codigo_producto=codigo_producto, tipo="revocacion",
            cantidad=-cantidad, origen="compra", external_id=external_id, note=note,
        ):
            logger.info("revocación duplicada ignorada (external_id=%s)", external_id)
            return False
        return True

    with transaction.atomic():
        acc = Account.objects.select_for_update().get(pk=account.pk)
        if not _movimiento_idempotente(
            account=acc, codigo_producto=codigo_producto, tipo="revocacion",
            cantidad=-cantidad, origen="compra", external_id=external_id, note=note,
        ):
            logger.info("revocación duplicada ignorada (external_id=%s)", external_id)
            return False

        # La misma traducción que hace `otorgar`, por el mismo motivo: el
        # `Derecho` vive en el producto OTORGADO, no en el comprado. Sin esto,
        # reembolsar un `pack_5_natal` buscaba un derecho de `pack_5_natal`
        # —que no existe—, lo creaba en 0, no bajaba nada y mandaba todo a
        # deuda: el usuario cobraba los US$ 149,90 y se quedaba con los cinco
        # informes. El código que llega del webhook es el que se PAGÓ, así que
        # la traducción tiene que pasar de este lado.
        prod = producto(codigo_producto)
        # Una vuelta por cada cosa que el producto otorgó: un combo dejó dos
        # derechos y el reembolso tiene que bajar los dos, o media compra
        # queda regalada.
        sin_cubrir = 0
        for codigo_otorgado, multiplicador in prod.otorga:
            unidades = cantidad * multiplicador
            derecho, _ = Derecho.objects.get_or_create(
                account=acc, codigo_producto=codigo_otorgado, defaults={"cantidad_restante": 0},
            )
            del_saldo = min(derecho.cantidad_restante or 0, unidades)
            derecho.cantidad_restante -= del_saldo
            derecho.save(update_fields=["cantidad_restante", "updated_at"])
            sin_cubrir += unidades - del_saldo

        acc.deuda += sin_cubrir
        acc.refund_count += 1
        if acc.refund_count >= settings.REFUND_FLAG_THRESHOLD:
            acc.flagged = True
        acc.save(update_fields=["deuda", "refund_count", "flagged"])
        account.deuda, account.refund_count, account.flagged = acc.deuda, acc.refund_count, acc.flagged
    return True


def puede(account, capacidad: str) -> bool:
    """¿La cuenta puede hacer esto?

    Es la única pregunta que hacen las vistas y las pantallas. Preguntar por
    producto obligaría a recorrerlas todas cada vez que se agrega un plan.
    """
    codigos = codigos_otorgados_por(capacidad)
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
