"""Acreditar y reembolsar una compra sin saber por qué pasarela entró.

El webhook de cada pasarela traduce su payload a estos dos verbos —cuánto se
pagó, en qué moneda, con qué id— y acá se decide qué derechos se otorgan o se
revocan. Lo que no puede saber de la pasarela lo fija el contrato de
import-linter «cobro no conoce pasarelas».

**La duplicación con `webhooks_stripe` es deliberada y temporal** (plan fase 1,
R11): `acreditar` reproduce `_entregar` + `_otorgar_y_marcar` y `reembolsar`
reproduce `_reembolsar`, con las mismas garantías y en el mismo orden. En la
fase 2 Stripe pasa a llamar a este módulo y la copia desaparece; hasta
entonces, un arreglo en uno de los dos lados hay que llevarlo al otro.

Política de errores, que quien llama traduce a su respuesta HTTP:

- `return False` con aviso al admin: fallo DEFINITIVO —ids vacíos, moneda o
  monto que no cierran, compra sin cuenta—. Reintentar no lo arregla: 200.
- `return False` SIN aviso: un reintento del mismo pago, ya aplicado. 200.
  Si además su informe ya arrancó (`informe_arrancado_at`), la repetición no
  toca nada más: ni adjudica, ni arranca, ni manda mail ni mide.
- `CompraDisputada`, `PagoDuplicado`: definitivos también, pero quien llama
  tiene que actuar (avisar; reembolsar el duplicado). Acá no se avisa, para
  que el aviso salga una sola vez y diga lo que se hizo.
- `CompraAnonimaSinMail` y cualquier otra excepción: el caller responde 5xx.
"""

import logging
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from api import analitica, catalogo, compra_anonima, devoluciones, disputas, notificaciones
from api.avisos import avisar_admin
from api.canje import MontoInvalido, aplicar_compra
from api.compra_service import arrancar_informe
from api.models import CuponUso, MailBloqueado, PasarelaCheckout, Reembolso

logger = logging.getLogger(__name__)

#: Cuánto se recuerda que ya se avisó el reembolso de un pago que no acreditó
#: la compra: cada `payment.updated` de ese pago y cada corrida de la
#: conciliación lo vuelven a ver.
_RECORDAR_AVISO_NO_ACREDITADO = 90 * 24 * 60 * 60


class CompraDisputada(Exception):
    """La fila tiene una disputa: esos fondos ya se los llevó la pasarela."""


class PagoDuplicado(Exception):
    """Otro pago aprobado sobre una fila ya acreditada con un pago distinto.

    Pasa de verdad en Mercado Pago (medido en sandbox): una preferencia admite
    más de un pago. No se otorga nada; quien llama lo reembolsa."""

    def __init__(self, pago_id: str, acreditado_por: str = ""):
        super().__init__(pago_id)
        self.pago_id = pago_id
        #: El pago que acreditó la fila, leído bajo el lock.
        self.acreditado_por = acreditado_por


class CompraAnonimaSinMail(Exception):
    """Una compra sin cuenta sin `mail_comprador`: no hay a quién adjudicarla.

    El checkout en pesos exige el mail antes de abrir la preferencia, así que
    esto es un bug nuestro, no un dato que falte del pago. Se avisa y se levanta
    para que el webhook responda 5xx: la notificación queda reintentándose a
    la vista hasta que alguien complete el mail y la compra se acredite."""


def avisar(texto: str) -> None:
    """El único punto por el que el cobro avisa al admin (hoy, Telegram)."""
    avisar_admin(texto)


#: Monedas que se facturan a mano (factura C ante ARCA) hasta tener la
#: emisión automática: cada venta acreditada avisa con lo necesario.
FACTURA_A_MANO = {"ars"}
_ARGENTINA = ZoneInfo("America/Argentina/Buenos_Aires")


def _pesos(centavos: int) -> str:
    """`$ 25.000,00`, como lo escribe el comprobante argentino."""
    return "$ " + f"{centavos / 100:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _avisar_venta_a_facturar(fila: PasarelaCheckout, cuenta, pago_id: str, monto: int) -> None:
    cuando = timezone.localtime(timezone.now(), _ARGENTINA)
    mail = (cuenta.email if cuenta else "") or fila.mail_comprador or ""
    avisar_venta(
        f"Venta en pesos para facturar (factura C, consumidor final): {_pesos(monto)} · "
        f"{cuando:%d/%m/%Y %H:%M} · {fila.codigo_producto} · "
        f"{compra_anonima.enmascarar(mail) if mail else 'sin mail'} · "
        f"pago {pago_id} · {fila.checkout_id}",
    )


def avisar_venta(texto: str) -> None:
    """Una venta que hay que facturar a mano (puente hasta la factura C
    automática contra ARCA, decisión del 19-10-2026). Mismo canal que
    `avisar`, separado para que «hubo un aviso» siga queriendo decir «algo
    raro pasó». La lista confiable es el admin de compras: esto es el empujón."""
    avisar_admin(texto)


def acreditar(
    fila: PasarelaCheckout, *, pago_id: str, monto_pagado: int, moneda: str, medio: str, external_id: str,
    a_mano: bool = False,
) -> bool:
    """Traduce un pago aprobado en derechos. Devuelve si esta llamada lo aplicó.

    `monto_pagado` es lo que se cobró (lista menos descuento), en centavos de
    `moneda`; `external_id` es la clave de idempotencia del ledger, con el
    prefijo de la pasarela (`mp:payment:<id>`); `pago_id` queda en
    `fila.pago_id` para atribuir después los reembolsos. `a_mano` entrega
    aunque la fila tenga una disputa: quien lo corre a mano ya miró.
    """
    if not pago_id or not external_id:
        # Sin `pago_id` ningún reembolso se podría atribuir a esta compra; sin
        # `external_id` el ledger guardaría "" y daría por aplicado el siguiente.
        logger.error(
            "compra %s: pago sin id (pago_id=%r, external_id=%r): no se acredita",
            fila.checkout_id, pago_id, external_id,
        )
        avisar(
            f"Compra {fila.checkout_id}: llegó un pago sin id (pago_id={pago_id!r}, "
            f"external_id={external_id!r}). No se acreditó.",
        )
        return False
    if _ya_arrancado(fila, pago_id):
        logger.info("compra %s: el pago %s ya se acreditó y su informe ya arrancó", fila.checkout_id, pago_id)
        return False
    _adjudicar_si_es_anonima(fila)
    cuenta = fila.account
    if cuenta is None:
        logger.error("compra %s pagada (%s) sin cuenta que la reclame: no se acredita", fila.checkout_id, pago_id)
        avisar(f"Pago {external_id} ({fila.checkout_id}): pagado y sin cuenta que lo reclame. No se acreditó.")
        return False

    # 14900 centavos de dólar no son 14900 de peso, y `aplicar_compra` sólo
    # compara enteros.
    moneda = (moneda or "").lower()
    if moneda != fila.moneda:
        logger.error(
            "compra %s: el pago %s vino en %s y la fila está en %s: no se acredita",
            fila.checkout_id, pago_id, moneda, fila.moneda,
        )
        avisar(
            f"Pago {external_id} ({fila.checkout_id}): vino en {moneda} y la fila está en {fila.moneda} "
            f"(monto {monto_pagado}). No se acreditó.",
        )
        return False

    if fila.vencido_at is not None and fila.acreditado_at is None:
        # EC15: un pago que llega después de que la fila venció. La plata entró
        # y manda; se entrega, y se mira por qué llegó tarde.
        logger.warning("compra %s pagada sobre una fila vencida: se acredita igual", fila.checkout_id)
        avisar(f"Pago {external_id} ({fila.checkout_id}): pago sobre una fila vencida; se acreditó igual.")

    codigo = fila.codigo_producto
    try:
        aplicado, arrancado = _otorgar_y_marcar(
            fila, cuenta, codigo, pago_id, monto_pagado, external_id, a_mano,
        )
    except MontoInvalido:
        # Ya lo logueó `aplicar_compra` con los dos montos.
        avisar(
            f"Pago {external_id} ({fila.checkout_id}): el monto no coincide (pagado {monto_pagado} "
            f"{fila.moneda}, lista {fila.precio_de_lista()}, descuento {fila.descuento_centavos}). No se acreditó.",
        )
        return False
    if arrancado:
        # Una repetición concurrente con la que arrancó el informe: la vio
        # recién bajo el lock.
        return False

    lang = fila.locale
    if aplicado:
        logger.info("compra %s acreditada por %s: %s", fila.checkout_id, external_id, codigo)
        # Dentro del `if aplicado`, que es lo que lo hace idempotente: un
        # reintento no cuenta la compra dos veces. El monto es LO PAGADO.
        analitica.evento(
            cuenta, "compra_completada",
            {
                "producto": codigo, "monto_centavos": monto_pagado, "locale": lang,
                "cupon": fila.cupon.codigo if fila.cupon_id and fila.descuento_centavos else None,
                "moneda": fila.moneda, "pasarela": fila.pasarela,
            },
        )
        # Acá y no después del arranque del informe: si el arranque falla la
        # excepción sube, y el reintento de la pasarela ya no acredita (code
        # review del 19-10). Mismo `if aplicado` que lo hace idempotente.
        if fila.moneda in FACTURA_A_MANO:
            _avisar_venta_a_facturar(fila, cuenta, pago_id, monto_pagado)
        if fila.cupon_id and fila.descuento_centavos > 0:
            _registrar_uso(fila, cuenta, codigo, monto_pagado, external_id)

    # Si el informe no arranca, la excepción sube y quien llama pide el
    # reintento (ver `webhooks_stripe._entregar`). La plata ya quedó
    # acreditada —el átomo cerró— y, mientras `informe_arrancado_at` siga
    # vacío, una repetición del mismo pago reintenta el arranque (idempotente:
    # `get_or_create`). Ése es el único reintento que hace MP (inmediato,
    # medido en sandbox). Si tampoco arranca, la red es el aviso de abajo y
    # `manage.py acreditar_pago <id>`, que repite este camino; el cron de MP
    # no reprocesa el pago que acreditó la fila. Un informe que sí arrancó y
    # quedó a medias lo termina `reanudar_informes`.
    informe_en_curso = False
    try:
        informe_en_curso = arrancar_informe(cuenta, fila)
        # Con informe o sin nada que arrancar: no hay que reintentarlo nunca.
        PasarelaCheckout.objects.filter(pk=fila.pk, informe_arrancado_at__isnull=True).update(
            informe_arrancado_at=timezone.now(),
        )
    except Exception:
        if aplicado:
            # Sólo la llamada que acreditó (los reintentos no repiten el
            # aviso): MP no reintenta tarde y el cron de MP no reprocesa el
            # pago que acreditó la fila, así que el aviso es la red.
            logger.exception("compra %s acreditada por %s y el informe no arrancó", fila.checkout_id, external_id)
            avisar(
                f"Pago {pago_id} ({fila.checkout_id}): acreditado, pero el informe NO arrancó. "
                "Revisar el log y arrancarlo a mano.",
            )
        raise
    finally:
        # Un solo mail por compra, sólo en la llamada que la acreditó, y
        # después del arranque porque es lo que dice cuál mandar.
        # `notificar` no lanza, así que no tapa la excepción del arranque.
        if aplicado:
            evento = "informe_en_curso" if informe_en_curso else "compra_acreditada"
            notificaciones.notificar(cuenta, evento, {"producto": codigo, "medio": medio}, lang=lang)
    return aplicado


def _ya_arrancado(fila: PasarelaCheckout, pago_id: str) -> bool:
    """La fila ya la acreditó ESTE pago y su informe ya arrancó (o no había
    nada que arrancar). Leído de la base, no de `fila`, que puede ser de antes.

    Sin lock a propósito: la marca sólo se pone, nunca se saca, así que si se
    ve puesta es definitiva. Si no se ve, sigue el camino normal, que vuelve a
    mirarla bajo el lock en `_otorgar_y_marcar`."""
    return PasarelaCheckout.objects.filter(
        pk=fila.pk, acreditado_at__isnull=False, pago_id=pago_id, informe_arrancado_at__isnull=False,
    ).exists()


def _adjudicar_si_es_anonima(fila: PasarelaCheckout) -> None:
    """Le pone cuenta a una compra sin cuenta por `fila.mail_comprador` (RF5),
    ANTES de todo lo que registra la compra contra la cuenta.

    El mail es el que se pidió al abrir el checkout, no el que informe la
    pasarela: en MP el pagador puede pagar con una cuenta de MP de otro mail."""
    if not fila.anonimo or fila.account_id is not None:
        return
    email = (fila.mail_comprador or "").strip()
    if not email:
        logger.error("compra sin cuenta %s pagada sin mail_comprador: no se acredita", fila.checkout_id)
        avisar(f"Compra sin cuenta {fila.checkout_id} pagada SIN mail del comprador. No se acreditó: revisar.")
        raise CompraAnonimaSinMail(fila.checkout_id)
    cuenta = compra_anonima.adjudicar(fila.checkout_id, email)
    fila.refresh_from_db(fields=["account", "cuenta_nueva"])
    if cuenta is not None:
        fila.account = cuenta
    if MailBloqueado.bloqueado(email):
        # R8: la plata entró, se entrega igual; pero se mira.
        logger.warning("compra %s: sin cuenta de un mail bloqueado; se acredita igual", fila.checkout_id)
        avisar(
            f"Compra {fila.checkout_id}: sin cuenta de un mail BLOQUEADO "
            f"({compra_anonima.enmascarar(email)}). Se acredita igual.",
        )


def _otorgar_y_marcar(fila, cuenta, codigo, pago_id, monto_pagado, external_id, a_mano=False) -> tuple[bool, bool]:
    """Otorga y marca la fila acreditada en UN átomo, con la fila bloqueada.
    Devuelve (si esta llamada otorgó, si ESTE pago ya la acreditó y su
    informe ya arrancó: entonces no se hace nada más).

    Con la fila bloqueada se miran dos cosas que pueden haber cambiado desde
    que quien llama la leyó:

    - Otro pago ya la acreditó (Ruling 1, RF11b). Los `external_id` de dos
      pagos distintos son distintos, así que la idempotencia de
      `aplicar_compra` no los frena: es este chequeo, serializado por el lock,
      el que impide que dos notificaciones concurrentes otorguen dos veces.
      Va antes que la disputa: el segundo pago es un duplicado aunque la
      compra esté disputada, y como duplicado se reembolsa.
    - Una disputa (EC16). `disputas` bloquea la misma fila, así que o ve
      `acreditado_at` y revoca, o deja la marca y acá no se entrega.
    """
    with transaction.atomic():
        bloqueada = (
            PasarelaCheckout.objects.select_for_update()
            .only("disputa_id", "acreditado_at", "pago_id", "informe_arrancado_at").get(pk=fila.pk)
        )
        if (
            bloqueada.acreditado_at is not None and bloqueada.pago_id == pago_id
            and bloqueada.informe_arrancado_at is not None
        ):
            return False, True
        if bloqueada.acreditado_at is not None and bloqueada.pago_id and bloqueada.pago_id != pago_id:
            logger.error(
                "compra %s ya acreditada por el pago %s: el pago %s es un duplicado, no se otorga",
                fila.checkout_id, bloqueada.pago_id, pago_id,
            )
            raise PagoDuplicado(pago_id, acreditado_por=bloqueada.pago_id)
        if bloqueada.disputa_id and not a_mano:
            logger.error("compra %s con disputa %s: no se entrega", fila.checkout_id, bloqueada.disputa_id)
            raise CompraDisputada(bloqueada.disputa_id)
        aplicado = aplicar_compra(
            cuenta, codigo, monto_pagado,
            external_id=external_id,
            sujeto=fila.sujeto,
            descuento_centavos=fila.descuento_centavos,
            precio_centavos=fila.precio_de_lista(),
            al_saldar_deuda=lambda: _marcar_saldo_deuda(fila),
        )
        # Fuera del `if aplicado`: un reintento tras un fallo tardío devuelve
        # False (ya aplicado) y la fila igual tiene que quedar marcada.
        fila.pago_id = pago_id
        fila.acreditado_at = bloqueada.acreditado_at or timezone.now()
        fila.save(update_fields=["pago_id", "acreditado_at"])
    return aplicado, False


def _registrar_uso(fila, cuenta, codigo, pagado, external_id) -> None:
    """La constancia del cupón, FUERA del átomo de la compra y sin poder
    revertirla: un fallo acá se loguea y la persona se queda con lo que pagó.
    Idempotente por `external_id`."""
    try:
        CuponUso.objects.get_or_create(
            external_id=external_id,
            defaults=dict(
                cupon=fila.cupon, account=cuenta, codigo_producto=codigo, checkout=fila,
                descuento_centavos=fila.descuento_centavos, monto_pagado_centavos=pagado,
                moneda=fila.moneda,
            ),
        )
    except IntegrityError:
        logger.exception(
            "no se pudo registrar el uso del cupón %s en %s; la compra queda acreditada igual",
            fila.cupon.codigo, external_id,
        )


def _marcar_saldo_deuda(fila) -> None:
    """RF5b: la compra saldó deuda y no hay informe. Corre dentro del átomo de
    `aplicar_compra`, antes de que la fila se marque acreditada."""
    PasarelaCheckout.objects.filter(pk=fila.pk).update(saldo_deuda=True)
    fila.saldo_deuda = True


def reembolsar(
    fila: PasarelaCheckout, *, pago_id: str, refund_id: str, monto: int, moneda: str, external_id: str,
) -> None:
    """Revoca lo comprado y anota como deuda lo que ya se usó.

    Nunca se le quita a nadie un informe entregado: `canje.revocar` baja el
    derecho hasta donde alcanza y el resto queda como deuda. `external_id`
    (`mp:refund:<id>`) es la constancia en `Reembolso.refund_id` y la clave
    del ledger: prefijado, no choca con los ids de Stripe ni con el del pago.

    `pago_id` es el pago reembolsado, y tiene que ser EL que acreditó la fila
    (`fila.pago_id`, Ruling 4). En MP una preferencia admite más de un
    pago: el duplicado que reembolsamos (`PagoDuplicado`) vuelve como
    `refunded` con la misma external_reference, y sin este chequeo revocaba el
    informe comprado con el pago legítimo.
    """
    if not refund_id or not external_id or not pago_id:
        # Sin id no hay constancia posible: el primero se guardaría con "" y
        # todos los siguientes se darían por aplicados. Sin `pago_id`, un ""
        # coincidiría con el `pago_id` vacío de una fila sin acreditar.
        logger.error(
            "reembolso sin id sobre %s (refund=%r, pago=%r): no se aplica", fila.checkout_id, refund_id, pago_id,
        )
        return

    # Los montos sólo se comparan en la moneda de la compra.
    moneda = (moneda or "").lower()
    if moneda != fila.moneda:
        logger.error(
            "reembolso %s en %s sobre una compra en %s: no se revoca", external_id, moneda, fila.moneda,
        )
        avisar(
            f"Reembolso {external_id}: vino en {moneda} y la compra {fila.checkout_id} está en "
            f"{fila.moneda}. No se revocó nada.",
        )
        return

    # `fila.account` puede ser None si la cuenta se borró después de comprar
    # (RF22): `revocar` lo contempla y registra el movimiento igual.
    with transaction.atomic():
        # Bloqueada: la cuenta de unidades lee `unidades_revocadas` y la
        # actualiza, y dos reembolsos (o un reembolso y una disputa) pueden
        # llegar a la vez. `of=("self",)`: `account` es nullable.
        fila = PasarelaCheckout.objects.select_for_update(of=("self",)).select_related("account").get(pk=fila.pk)
        if fila.pago_id != pago_id:
            # Incluye la fila sin acreditar (`pago_id` vacío): ningún
            # pago es suyo. No se revoca ni se deja `Reembolso`. Puede ser el
            # duplicado que reembolsamos o un pago que no se pudo acreditar
            # (monto, moneda): acá no se sabe, así que no se lo llama de una
            # forma ni de la otra.
            logger.error(
                "reembolso %s del pago %s sobre %s, acreditada por %r: no se revoca",
                external_id, pago_id, fila.checkout_id, fila.pago_id,
            )
            aviso = None
            # Sin `Reembolso` no queda constancia en la base: la caché (la de
            # la base en producción) hace que el aviso salga una vez por
            # reembolso. `add` es atómico: dos notificaciones a la vez avisan una.
            if cache.add(f"cobro:aviso:reembolso_no_acreditado:{external_id}", True, _RECORDAR_AVISO_NO_ACREDITADO):
                aviso = (
                    f"Compra {fila.checkout_id}: reembolso de un pago que no acreditó la compra. "
                    f"Reembolso {external_id} del pago {pago_id}; la compra la acreditó el pago "
                    f"{fila.pago_id or '(ninguno)'}. No se revocó nada."
                )
        elif Reembolso.objects.filter(refund_id=external_id).exists():
            logger.info("reembolso %s ya aplicado", external_id)
            return
        else:
            aviso = _revocar(fila, external_id, monto)
    # Después del commit, una sola vez.
    if aviso:
        avisar(aviso)


def _revocar(fila, external_id: str, monto: int) -> str | None:
    """La revocación de `reembolsar`, con la fila ya bloqueada. Devuelve el
    aviso a mandar después del commit, si hay."""
    prod = catalogo.producto(fila.codigo_producto)
    base = devoluciones.pagado(fila)
    if not devoluciones.cubre_todo(fila, monto) and len(prod.otorga) != 1:
        # Un combo devuelto a medias no tiene respuesta obvia: no se revoca
        # nada, pero el monto se anota y queda la constancia.
        Reembolso.objects.create(refund_id=external_id, fila=fila, monto=monto)
        devoluciones.registrar(fila, 0, monto)
        logger.error("reembolso %s parcial sobre el combo %s: no se revoca", external_id, fila.codigo_producto)
        aviso = (
            f"Reembolso {external_id}: parcial ({monto} {fila.moneda}) sobre el combo "
            f"{fila.codigo_producto} {fila.checkout_id}. No se revocó nada: resolver a mano."
        )
    else:
        aviso = None
        # Proporción redondeada HACIA ARRIBA y nunca más de lo que queda
        # sin revocar (ver `devoluciones`).
        pedidas = devoluciones.unidades_pedidas(fila, monto)
        unidades = min(pedidas, devoluciones.quedan(fila))
        if unidades and devoluciones.revocar_unidades(fila, unidades, external_id) is None:
            logger.info("reembolso %s ya revocado en el ledger", external_id)
            return None
        tomadas, cedido = disputas.ceder_a_reembolso(fila, pedidas - unidades, monto)
        Reembolso.objects.create(refund_id=external_id, fila=fila, monto=monto, unidades=unidades + tomadas)
        # Lo que la disputa ya había anotado de este monto no se suma dos veces.
        devoluciones.registrar(fila, unidades, monto - cedido)
        logger.info(
            "reembolso %s (%s de %s): revocadas %s unidades de %s, %s tomadas de una disputa",
            external_id, monto, base, unidades, fila.codigo_producto, tomadas,
        )
    return aviso
