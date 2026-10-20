"""Disputas de Stripe (RF15, EC11, EC16): retirar y reponer.

Una disputa que retira fondos se trata como un reembolso de lo que queda sin
devolver: se revoca lo que corresponde, se avisa y se bloquea el mail. Si
Stripe devuelve los fondos, se repone exactamente lo que se revocó y el mail
se libera cuando no le queda ninguna disputa abierta.

La constancia de que un evento ya se aplicó es la fila `Disputa`, no la marca
`disputa_id` de la compra (que se borra al reponer) ni el ledger (que no se
mueve en todas las ramas). Stripe reentrega y no garantiza el orden.

Todo `return` es definitivo y el webhook responde 200: acá ya se le preguntó a
Stripe por la sesión, así que reintentar no hace aparecer una compra que no
está. Cada rama es un átomo sobre la compra bloqueada; el aviso sale después
del commit, una sola vez.
"""

import logging

from django.db import transaction
from django.utils import timezone

from api import compra_anonima, devoluciones
from api.avisos import avisar_admin
from api.canje import aplicar_compra, otorgar
from api.models import Disputa, MailBloqueado, PasarelaCheckout
from api.stripe_client import sesion_por_payment_intent

logger = logging.getLogger(__name__)

RETIRO = "charge.dispute.funds_withdrawn"
REPOSICION = "charge.dispute.funds_reinstated"
EVENTOS = (RETIRO, REPOSICION)


def procesar(dispute: dict, tipo: str) -> None:
    dispute_id = dispute.get("id", "")
    pi = dispute.get("payment_intent") or ""
    monto = dispute.get("amount") or 0
    moneda = (dispute.get("currency") or "").lower()
    fila, sesion = _fila_de_disputa(dispute)
    if fila is None:
        logger.error("disputa %s sin compra conocida (pi=%s): no se toca nada", dispute_id, pi)
        avisar_admin(f"Stripe disputa {dispute_id} ({tipo}) sobre {pi}: no encuentro la compra. {monto} {moneda}.")
        return

    if tipo == RETIRO:
        aviso = _retirar(fila.pk, sesion, dispute_id, monto, moneda, dispute.get("reason"))
    else:
        aviso = _reponer(fila.pk, dispute_id)
    if aviso:
        avisar_admin(aviso)


def _fila_de_disputa(dispute: dict) -> tuple:
    """`(fila, sesion)` de esta disputa. Primero por el `payment_intent` de la
    fila; si la disputa llegó antes que `completed` (EC16) la fila todavía no
    lo tiene, y se pregunta a Stripe de qué sesión es. `sesion` es None cuando
    alcanzó con la fila."""
    pi = dispute.get("payment_intent") or ""
    if not pi:
        # Buscar por vacío engancharía cualquier fila abierta.
        return None, None
    fila = PasarelaCheckout.objects.filter(pago_id=pi).first()
    if fila is not None:
        return fila, None
    sesion = sesion_por_payment_intent(pi)
    if sesion is None:
        return None, None
    return PasarelaCheckout.objects.filter(checkout_id=sesion.get("id", "")).first(), sesion


def _mail_de_disputa(fila, sesion) -> str:
    """De quién bloquear el mail. Una compra sin cuenta disputada antes de su
    `completed` (EC16) todavía no tiene cuenta: el mail sale del pago. Sin
    pago que lo traiga (Mercado Pago, o una cuenta borrada después de
    comprar), el que se pidió al abrir el checkout (Ruling 16). En las filas
    de Stripe `mail_comprador` es "": para ellas no cambia nada."""
    if fila.account is not None:
        return fila.account.email or ""
    return ((sesion or {}).get("customer_details") or {}).get("email") or fila.mail_comprador or ""


def _bloquear_fila(fila_pk):
    # `of=("self",)`: `account` es nullable y el JOIN es OUTER; Postgres no
    # acepta FOR UPDATE sobre ese lado (medido 13-10-2026, SQLite lo ignora).
    return PasarelaCheckout.objects.select_for_update(of=("self",)).select_related("account").get(pk=fila_pk)


def ceder_a_reembolso(fila, unidades: int, monto: int) -> tuple[int, int]:
    """Pasa hasta `unidades` ya revocadas por una disputa ABIERTA de la compra
    —y hasta `monto` de lo que esa disputa anotó— a la cuenta de un
    reembolso. Devuelve `(unidades, monto)` cedidos. Corre con la compra
    bloqueada por quien reembolsa.

    Stripe no ordena los eventos: el reembolso de una disputa ya ganada puede
    llegar antes que su `funds_reinstated`. Sin esto, el reembolso no
    encontraba unidades que revocar (las tenía la disputa) y la reposición
    las devolvía todas: producto y plata. Lo que la disputa conserva pasa a
    ser unidades sueltas, que es como se van a reponer.

    Si la disputa se termina perdiendo, la compra igual queda bien (las
    unidades siguen revocadas y el monto anotado una vez); lo que cambia es
    de cuál de las dos constancias cuelga. Stripe no deja reembolsar un cargo
    con una disputa abierta, así que el caso pide un reembolso en etapa de
    consulta."""
    disputa = (
        Disputa.objects.select_for_update()
        .filter(fila=fila, estado=Disputa.ABIERTA, unidades_revocadas__gt=0)
        .order_by("created_at", "pk").first()
    )
    if disputa is None or unidades <= 0:
        return 0, 0
    tomadas = min(unidades, disputa.unidades_revocadas)
    cedido = min(monto, disputa.monto_anotado)
    codigo, _total = devoluciones.unidades_de(fila)
    disputa.unidades_revocadas -= tomadas
    disputa.monto_anotado -= cedido
    disputa.revocado_codigo, disputa.revocado_cantidad = codigo, disputa.unidades_revocadas
    disputa.revocado_entera = False
    disputa.cedido_a_reembolso = True
    disputa.save(update_fields=[
        "unidades_revocadas", "monto_anotado", "revocado_codigo", "revocado_cantidad", "revocado_entera",
        "cedido_a_reembolso",
    ])
    return tomadas, cedido


def _bloquear_y_lockear(email: str, dispute_id: str) -> None:
    """Bloquea el mail y deja lockeada su fila de `MailBloqueado` hasta el
    commit. Si una reposición concurrente la borró entre el alta y el lock, la
    vuelve a crear: el mail de una disputa abierta no puede quedar libre."""
    if not email:
        return
    for _ in range(2):
        MailBloqueado.bloquear(email, motivo="disputa", dispute_id=dispute_id)
        if MailBloqueado.objects.select_for_update().filter(email=email).exists():
            return
    raise RuntimeError(f"no se pudo bloquear el mail de la disputa {dispute_id}")  # 5xx: Stripe reintenta


def _lockear_bloqueo(email: str):
    """La fila de `MailBloqueado` de ese mail, lockeada, o None. La reposición
    sólo borra esta fila: un bloqueo que otra disputa cree después no lo
    toca, aunque todavía no lo vea."""
    if not email:
        return None
    return MailBloqueado.objects.select_for_update().filter(email=email).first()


def _retirar(fila_pk, sesion, dispute_id, monto, moneda, motivo) -> str | None:
    with transaction.atomic():
        fila = _bloquear_fila(fila_pk)
        if Disputa.objects.filter(dispute_id=dispute_id).exists():
            # Reentrega, o un retiro que llega después de su reposición: en los
            # dos casos ya no hay nada que aplicar.
            logger.info("disputa %s ya registrada: el retiro no se aplica de nuevo", dispute_id)
            return None
        mail = MailBloqueado.normalizar(_mail_de_disputa(fila, sesion))
        _bloquear_y_lockear(mail, dispute_id)
        disputa = Disputa.objects.create(dispute_id=dispute_id, fila=fila, email=mail)
        fila.disputa_id = dispute_id
        fila.save(update_fields=["disputa_id"])

        if moneda != fila.moneda:
            # Los montos no se comparan entre monedas: no se revoca nada solo.
            # Pero la disputa existe y retiró fondos: queda registrada (un
            # reenvío no vuelve a avisar) y el mail se bloquea igual.
            hecho = f"vino en {moneda} y la compra está en {fila.moneda}: no se revocó, resolver a mano. Mail bloqueado"
            logger.error("disputa %s en %s sobre compra en %s: no se revoca", dispute_id, moneda, fila.moneda)
        elif fila.acreditado_at is None:
            # EC16: sin entregar no hay nada que revocar; la marca alcanza
            # para que el `completed` que llegue después no entregue.
            # `acreditado_at` se lee con la fila bloqueada: `_entregar` lo pone
            # en su propio átomo sobre la misma fila, nunca está a medias.
            hecho = "todavía sin entregar: no se entrega. Mail bloqueado"
        else:
            hecho = _revocar_lo_que_queda(fila, disputa, monto)
    logger.warning("disputa %s aplicada sobre %s: %s", dispute_id, fila.checkout_id, hecho)
    return (
        f"⚠️ Disputa {dispute_id} ({motivo}): {fila.codigo_producto} {fila.checkout_id}, "
        f"{monto} {moneda}. {hecho}: {compra_anonima.enmascarar(mail) if mail else 'sin mail'}."
    )


def _revocar_lo_que_queda(fila, disputa, monto) -> str:
    """Trata la disputa como el reembolso de lo que todavía no se devolvió:
    revoca las unidades que quedan y anota el monto, sin pasar de lo pagado
    aunque Stripe dispute el cargo entero. Guarda en `disputa` qué hizo, para
    deshacer exactamente eso si Stripe devuelve los fondos."""
    sin_devolver = max(0, devoluciones.pagado(fila) - fila.reembolsado_centavos)
    unidades = devoluciones.quedan(fila)
    if not sin_devolver and not unidades:
        return "ya reembolsada; no se revoca de nuevo. Mail bloqueado"
    revocado = None
    if unidades:
        revocado = devoluciones.revocar_unidades(fila, unidades, f"stripe:dispute:{disputa.dispute_id}")
    anotado = min(monto, sin_devolver)
    devoluciones.registrar(fila, unidades if revocado else 0, anotado)
    if revocado:
        disputa.revocado_codigo, disputa.revocado_cantidad, disputa.revocado_entera = revocado
        disputa.unidades_revocadas = unidades
    disputa.monto_anotado = anotado
    disputa.save(update_fields=[
        "revocado_codigo", "revocado_cantidad", "revocado_entera", "unidades_revocadas", "monto_anotado",
    ])
    if revocado:
        return "Revocado y mail bloqueado"
    return "Nada que revocar (ya revocado por un reembolso). Mail bloqueado"


def _reponer(fila_pk, dispute_id) -> str | None:
    with transaction.atomic():
        fila = _bloquear_fila(fila_pk)
        disputa = Disputa.objects.select_for_update().filter(dispute_id=dispute_id).first()
        if disputa is None:
            # La reposición llegó antes que el retiro (Stripe no garantiza el
            # orden). Se registra resuelta: el retiro que llegue después ya no
            # se aplica, y un reenvío de esta no vuelve a avisar.
            Disputa.objects.create(
                dispute_id=dispute_id, fila=fila, estado=Disputa.RESUELTA, resuelta_at=timezone.now(),
            )
            logger.error("disputa %s: fondos devueltos sin retiro previo registrado", dispute_id)
            return (
                f"Stripe disputa {dispute_id}: fondos devueltos sobre {fila.checkout_id} "
                "sin retiro previo registrado."
            )
        if disputa.estado == Disputa.RESUELTA:
            logger.info("disputa %s ya repuesta", dispute_id)
            return None

        bloqueo = _lockear_bloqueo(disputa.email)
        estado = _devolver_lo_revocado(fila, disputa)
        disputa.estado, disputa.resuelta_at = Disputa.RESUELTA, timezone.now()
        disputa.save(update_fields=["estado", "resuelta_at"])
        mail = _desbloquear_si_no_quedan_abiertas(disputa.email, bloqueo)
        # La marca ya no dice nada cierto: dejada puesta haría que un
        # `completed` reentregado avisara «compra ya disputada» sobre una que
        # no lo está. En el mismo átomo que la reposición.
        fila.disputa_id = None
        fila.save(update_fields=["disputa_id"])
    logger.info("disputa %s resuelta a favor sobre %s: %s", dispute_id, fila.checkout_id, estado)
    return f"Disputa {dispute_id} resuelta a favor: {fila.checkout_id} {estado}; {mail}."


def _devolver_lo_revocado(fila, disputa) -> str:
    """Deshace lo que hizo el retiro: devuelve las unidades que revocó y
    resta de la compra el monto que anotó, así la compra deja de contar como
    reembolsada y un reembolso real posterior revoca lo que corresponde."""
    devoluciones.registrar(fila, -disputa.unidades_revocadas, -disputa.monto_anotado)
    repuesto_id = f"stripe:dispute:{disputa.dispute_id}:reinstated"
    if fila.acreditado_at is None:
        # EC16: la disputa llegó antes que la entrega. Con la marca borrada
        # (abajo), un `completed` que llegue ahora entrega solo; uno que ya
        # llegó se rechazó por la disputa y no se repite.
        return (
            "nunca se entregó: si su pago llega, se entrega solo; si ya había llegado, "
            "acreditar a mano con acreditar_sesion"
        )
    if not disputa.revocado_cantidad and disputa.cedido_a_reembolso:
        return "lo que el retiro revocó pasó a cubrir un reembolso, no se repone"
    if not disputa.revocado_cantidad:
        # El retiro no revocó nada (ya estaba reembolsada o revocada, o vino
        # en otra moneda): reponer ahora regalaría producto.
        return "el retiro no había revocado nada, no se repone"
    if fila.account is None:
        # La cuenta se borró después de comprar (RF22): no hay a quién
        # reponerle, y reintentar no lo cambia.
        logger.error("disputa %s resuelta a favor sobre una cuenta borrada: no se repone", disputa.dispute_id)
        return "la cuenta se borró, no hay a quién reponerle"
    if disputa.revocado_entera:
        # Se revocó la compra entera: se repone como compra, con otro
        # `external_id` que el de la sesión (con el mismo, `aplicar_compra`
        # la descartaría como duplicada).
        aplicar_compra(
            fila.account, fila.codigo_producto, devoluciones.pagado(fila),
            external_id=repuesto_id, sujeto=fila.sujeto,
            descuento_centavos=fila.descuento_centavos, precio_centavos=fila.precio_de_lista(),
        )
    else:
        # Se revocaron unidades sueltas (había reembolsos parciales antes):
        # vuelven esas, no el pack entero. `otorgar` salda deuda primero.
        otorgar(
            fila.account, disputa.revocado_codigo, disputa.revocado_cantidad,
            origen="compra", external_id=repuesto_id,
        )
    return "repuesto"


def _desbloquear_si_no_quedan_abiertas(email: str, bloqueo) -> str:
    """Libera el mail si ya no le queda ninguna disputa abierta, y dice qué
    pasó. Sólo borra `bloqueo`, la fila que esta reposición lockeó. Un
    bloqueo puesto a mano (otro `motivo`) no lo levanta una disputa."""
    if not email:
        return "sin mail bloqueado"
    if Disputa.objects.filter(email=email, estado=Disputa.ABIERTA).exists():
        return "el mail sigue bloqueado: tiene otra disputa abierta"
    if bloqueo is None:
        return "el mail no estaba bloqueado"
    if bloqueo.motivo != "disputa":
        return "el mail sigue bloqueado: el bloqueo es a mano"
    bloqueo.delete()
    return "mail desbloqueado"
