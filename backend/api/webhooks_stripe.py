"""El webhook de Stripe: por acá entra la plata.

Despacha siete eventos, que el endpoint del dashboard de Stripe (live y
sandbox) tiene que tener dados de alta a mano —ver el CLAUDE.md del repo—:
`checkout.session.completed` y `checkout.session.async_payment_succeeded`
(acreditar), `refund.created` (revocar), `checkout.session.expired` y
`checkout.session.async_payment_failed` (vencer y descartar), y
`charge.dispute.funds_withdrawn` y `charge.dispute.funds_reinstated`
(revertir por disputa, y reponer si Stripe devuelve los fondos).

La URL es pública, así que la firma es la única autenticación. Sin
`STRIPE_WEBHOOK_SECRET` configurado se rechaza todo (fail-closed): aceptar
entregas cuando falta la configuración es la peor forma de fallar en un
endpoint por el que se acreditan informes pagos.

**La política de errores es la inversa de la de Polar**, y es a propósito.
Polar deshabilita el endpoint tras diez entregas fallidas seguidas, así que
allá se responde 2xx a todo y cualquier error se pierde: una compra que falla
al acreditar no vuelve a intentarse nunca. Stripe reintenta durante tres días
con backoff y no deshabilita nada, entonces acá:

- fallo transitorio (la API no responde, la base se cayó) → **5xx**, y la
  compra se acredita en algún reintento;
- fallo definitivo (un precio que no mapeamos, un monto que no coincide) →
  **200**, porque reintentar no lo va a arreglar;
- firma inválida → **403**.
"""

import logging

from django.conf import settings
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


from api import cobro, compra_anonima, disputas
from api.models import PasarelaCheckout
from api.stripe_client import (
    FirmaInvalida, codigo_de_product, obtener_sesion, verificar_firma,
)

logger = logging.getLogger(__name__)

# Los dos eventos de pago. `completed` puede llegar con la plata todavía no
# acreditada —hay medios de pago que no son instantáneos—, y en ese caso el que
# vale es `async_payment_succeeded`. Los dos recorren el mismo camino: lo que
# decide si se acredita es `payment_status`, no el nombre del evento.
EVENTOS_PAGO = ("checkout.session.completed", "checkout.session.async_payment_succeeded")

# `refund.created` y no `charge.refunded`: desde la actualización de octubre
# de 2024 es el evento consistente para todos los tipos de reembolso, y trae
# el detalle sin una llamada extra a la API.
EVENTOS_REEMBOLSO = ("refund.created",)

# La sesión venció sin pagarse (`VENCIMIENTO_SESION` en `stripe_client`), o el
# medio de pago asincrónico falló. No mueven plata: marcan la fila para que la
# cuenta deje de mostrar un pago que nadie hizo, y descartan la carta de una
# compra sin cuenta (RF8). `async_payment_failed` hace falta aparte: con
# Managed Payments un medio asincrónico que falla deja la sesión `complete` y
# `expired` no llega nunca, así que sin él la carta anónima quedaba guardada
# para siempre.
EVENTOS_VENCIMIENTO = ("checkout.session.expired", "checkout.session.async_payment_failed")

# Stripe retiró los fondos por una disputa (o los devolvió): ver `api/disputas.py`.
EVENTOS_DISPUTA = disputas.EVENTOS


class StripeWebhookView(APIView):
    # La firma es la autenticación: `AllowAny` no apaga nada más (ver el
    # hallazgo del review del CMS), sólo dice que acá no hay sesión que valga.
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def post(self, request):
        secreto = settings.STRIPE_WEBHOOK_SECRET
        if not secreto:
            logger.error("STRIPE_WEBHOOK_SECRET no configurado: se rechaza la entrega")
            return Response(status=status.HTTP_403_FORBIDDEN)

        try:
            evento = verificar_firma(
                request.body, request.headers.get("Stripe-Signature", ""), secreto,
            )
        except FirmaInvalida as e:
            logger.warning("entrega de stripe rechazada: %s", e)
            return Response(status=status.HTTP_403_FORBIDDEN)

        tipo = evento.get("type", "")
        objeto = (evento.get("data") or {}).get("object") or {}
        if tipo not in EVENTOS_PAGO + EVENTOS_REEMBOLSO + EVENTOS_VENCIMIENTO + EVENTOS_DISPUTA:
            logger.info("evento de stripe ignorado: %s", tipo)
            return Response(status=status.HTTP_200_OK)

        try:
            if tipo in EVENTOS_PAGO:
                _acreditar(objeto.get("id", ""))
            elif tipo in EVENTOS_VENCIMIENTO:
                _vencer(objeto.get("id", ""))
            elif tipo in EVENTOS_DISPUTA:
                disputas.procesar(objeto, tipo)
            else:
                _reembolsar(objeto)
        except Exception:
            # Transitorio hasta que se demuestre lo contrario: se pide el
            # reintento en vez de perder la operación. Lo definitivo ya salió
            # por `return` adentro de cada función.
            logger.exception("entrega de stripe %s fallida: se pide reintento", tipo)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)


def _vencer(session_id: str) -> None:
    """La sesión venció sin pagarse, o su pago asincrónico falló: la fila deja
    de ser un pago en curso.

    Un solo `update` condicional, y por eso idempotente y sin carrera con el
    pago: si la fila ya está acreditada no se toca (la plata manda), y si ya
    está vencida el segundo evento no cambia la fecha. No consulta a Stripe:
    el evento alcanza y no hay monto que validar. Sin fila es definitivo —200—,
    porque reintentar no la va a hacer aparecer.
    """
    marcadas = PasarelaCheckout.objects.filter(
        checkout_id=session_id, acreditado_at__isnull=True, vencido_at__isnull=True,
    ).update(vencido_at=timezone.now())
    if not marcadas:
        logger.info("sesión %s vencida sin fila abierta que marcar", session_id)
    # Una compra sin cuenta que no se pagó no deja nada guardado (RF8). Corre
    # también si la fila ya estaba vencida: es idempotente y repara un
    # reintento tras un fallo a mitad.
    compra_anonima.descartar(session_id)


def _product_de(sesion: dict) -> str:
    """El Product de Stripe del único line item. Con `price_data` Stripe crea
    un Price efímero por sesión: su id no dice nada, el Product sí."""
    items = ((sesion.get("line_items") or {}).get("data")) or []
    if not items:
        return ""
    return ((items[0].get("price") or {}).get("product")) or ""


def _acreditar(session_id: str) -> None:
    """Traduce una sesión pagada en un pago para `cobro.acreditar`.

    Acá queda sólo lo que es de Stripe: el estado del pago, el Product, el
    descuento contra la sesión, el subtotal y el aviso de impuesto. Lo que
    decide plata —disputa, moneda, fila vencida, otorgar, cupón usado, aviso,
    informe— lo hace `cobro`, igual que para Mercado Pago.

    Los `return` de acá son fallos DEFINITIVOS: se loguean y la entrega se
    responde 200, porque ningún reintento los arregla. Lo que sí puede
    arreglarse reintentando se deja propagar, y la vista responde 5xx.
    """
    sesion = obtener_sesion(session_id)

    if sesion.get("payment_status") != "paid":
        # Lista blanca, no lista negra. El tercer valor posible es
        # `no_payment_required`, que aparece con un cupón del 100%: con una
        # lista negra se acreditaría un informe sin haber cobrado nada.
        logger.info(
            "sesión %s con payment_status=%s: no se acredita todavía",
            session_id, sesion.get("payment_status"),
        )
        return

    fila = (
        PasarelaCheckout.objects.filter(checkout_id=session_id).select_related("cupon", "account").first()
    )
    if fila is None:
        # R3 (fase 2): toda sesión se abre con su fila desde 2026-09 y vence a
        # las 24 h. Sin fila no hay moneda ni precio congelados contra los que
        # validar: no se adivina, se acredita a mano.
        logger.error("sesión %s pagada sin fila de checkout: no se acredita", session_id)
        cobro.avisar(f"Stripe {session_id}: pagada SIN fila de checkout. No se acreditó: acreditar a mano.")
        return

    # Antes de validar Product y monto, y a propósito: si alguno falla, la
    # entrega responde 200 sin acreditar, pero la fila ya tiene el mail con el
    # que `cobro` la adjudica, y `manage.py acreditar_sesion` puede
    # resolverla. Sin mail, `cobro` levanta `CompraAnonimaSinMail` (5xx).
    _completar_mail_si_es_anonima(fila, sesion)

    # El Product de la sesión dice qué cobró Stripe; la fila dice qué abrimos.
    # Los dos tienen que coincidir: elegir uno solo es entregar de más o de menos.
    product_id = _product_de(sesion)
    try:
        codigo_sesion = codigo_de_product(product_id)
    except KeyError:
        logger.error("sesión %s con un Product que no mapeamos (%s): no se acredita", session_id, product_id)
        cobro.avisar(f"Stripe {session_id}: Product {product_id} no está en STRIPE_PRODUCTOS. No se acreditó.")
        return
    if fila.codigo_producto != codigo_sesion:
        logger.error(
            "sesión %s: el checkout era de %s y la sesión dice %s", session_id, fila.codigo_producto, codigo_sesion,
        )
        cobro.avisar(
            f"Stripe {session_id}: la fila es de {fila.codigo_producto} y la sesión trae {product_id} "
            f"({codigo_sesion}). No se acreditó.",
        )
        return

    monto = sesion.get("amount_subtotal")
    if monto is None:
        # `aplicar_compra` levantaría `MontoInvalido` con un `None != 2900` que
        # se lee como "el monto no coincide", que es otro problema con otro
        # arreglo. Se rechaza acá, con su propio log.
        logger.error("sesión %s sin monto (amount_subtotal nulo): no se acredita", session_id)
        cobro.avisar(f"Stripe {session_id}: sin amount_subtotal. No se acreditó.")
        return

    _avisar_si_el_precio_no_lleva_el_impuesto_incluido(session_id, sesion, monto)

    try:
        descuento, _cupon = _descuento_de(session_id, sesion, fila)
    except DescuentoNoCierra:
        # Ya logueado con los tres valores. Reintentar no lo arregla: lo
        # resuelve a mano `manage.py acreditar_sesion`.
        return

    # `amount_subtotal` y no `amount_total`: MEDIDO el 03-09-2026 contra una
    # sesión pagada de verdad con dirección española. Con Managed Payments el
    # subtotal NO baja —el impuesto va aparte, en `total_details`—, así que
    # vale el precio de lista en la moneda de la sesión, con impuesto incluido
    # o encima. Con cupón (medido el 06-09-2026) tampoco baja: el descuento va
    # en `total_details.amount_discount`, y acá se resta el congelado.
    try:
        cobro.acreditar(
            fila, pago_id=_payment_intent_id(sesion), monto_pagado=monto - descuento,
            moneda=sesion.get("currency") or "", medio=_medio_de_pago(sesion),
            external_id=f"stripe:session:{session_id}",
        )
    except cobro.CompraDisputada as e:
        # EC16: esos fondos ya se los llevó Stripe; entregar sería regalar lo
        # disputado. Ya logueado bajo el lock.
        cobro.avisar(f"Stripe {session_id}: llegó el pago de una compra ya disputada ({e}). No se entregó.")
    except cobro.PagoDuplicado as e:
        # En Stripe no debería pasar: una sesión, un PaymentIntent. Si pasa,
        # no se otorga y se mira a mano.
        cobro.avisar(
            f"Stripe {session_id}: el pago {e.pago_id} llegó sobre una compra ya acreditada por "
            f"{e.acreditado_por}. No se otorgó: revisar y reembolsar a mano si corresponde.",
        )


def _completar_mail_si_es_anonima(fila: PasarelaCheckout, sesion: dict) -> None:
    """Una compra sin cuenta se adjudica por `fila.mail_comprador` (`cobro`).
    En Stripe el mail lo pide Checkout, no nosotros: se copia acá del pago.

    Sin mail no se guarda nada: `cobro` levanta `CompraAnonimaSinMail`, avisa
    y la vista pide el reintento. Stripe siempre pide el mail (verificado en
    sandbox con Managed Payments, 07-10-2026): si falta es transitorio o un
    cambio de Stripe (RF7)."""
    if not fila.anonimo or fila.account_id is not None or fila.mail_comprador:
        return
    email = ((sesion.get("customer_details") or {}).get("email") or "").strip()
    if not email:
        return
    fila.mail_comprador = email
    fila.save(update_fields=["mail_comprador"])


class DescuentoNoCierra(Exception):
    """La sesión trae un descuento que no es el que congelamos al abrir."""


def _descuento_de(session_id: str, sesion: dict, fila) -> tuple[int, object]:
    """`(descuento, cupon)` con los que se acredita, validando la sesión contra
    la fila congelada al abrir el checkout.

    La autoridad es NUESTRA fila, no Stripe: el descuento que se le pasa a
    `aplicar_compra` sale de acá, y así su `monto == precio − descuento` sigue
    comparando dos fuentes independientes. Tres cosas tienen que cerrar: el
    promotion code de la sesión es exactamente el nuestro, el descuento que
    Stripe reporta es el congelado, y (lo chequea `aplicar_compra`) el
    subtotal es el precio de lista.

    La única combinación distinta que se acredita, MEDIDA en sandbox el
    06-09-2026: el cupón se agotó entre abrir y pagar, Stripe le quitó el
    descuento y cobró la lista. Llega sin `discounts` y con `amount_discount`
    en 0 aunque la fila tenga cupón. La persona pagó entero: se acredita
    entero, sin contar un uso del cupón.
    """
    reportado = (sesion.get("total_details") or {}).get("amount_discount") or 0
    promos = [d.get("promotion_code") for d in (sesion.get("discounts") or [])]
    esperado = fila.descuento_centavos if fila is not None else 0
    cupon = fila.cupon if fila is not None else None

    if cupon is None or esperado == 0:
        if promos or reportado:
            # A1: un descuento que nuestra base no conoce. Es la puerta que
            # `allow_promotion_codes` abriría, y se queda cerrada acá también.
            logger.error(
                "sesión %s trae un descuento que no abrimos nosotros (promos=%s, "
                "amount_discount=%s): no se acredita", session_id, promos, reportado,
            )
            cobro.avisar(
                f"Stripe {session_id}: el descuento no cierra (promos={promos}, reportado={reportado}). "
                "No se acreditó.",
            )
            raise DescuentoNoCierra
        return 0, None

    if not promos and reportado == 0:
        logger.warning(
            "sesión %s: cupón %s removido por Stripe (se agotó entre abrir y pagar); "
            "se acredita a precio de lista sin contar el uso", session_id, cupon.codigo,
        )
        fila.descuento_centavos = 0
        fila.save(update_fields=["descuento_centavos"])
        return 0, None

    if promos != [cupon.stripe_promotion_code_id] or reportado != esperado:
        logger.error(
            "sesión %s: el descuento no cierra contra la fila. cupón=%s promo esperado=%s "
            "promos=%s descuento esperado=%s reportado=%s: no se acredita",
            session_id, cupon.codigo, cupon.stripe_promotion_code_id, promos, esperado, reportado,
        )
        cobro.avisar(
            f"Stripe {session_id}: el descuento no cierra (promos={promos}, reportado={reportado}). "
            "No se acreditó.",
        )
        raise DescuentoNoCierra
    return esperado, cupon


def _payment_intent_id(sesion: dict) -> str:
    """El PI expandido es un dict; en sesiones viejas (y en los tests) es el id."""
    pi = sesion.get("payment_intent")
    if isinstance(pi, dict):
        return pi.get("id") or ""
    return pi or ""


def _medio_de_pago(sesion: dict) -> str:
    """El `type` del PaymentMethod usado (`pix`, `card`, ...); vacío si el PI no
    vino expandido. `payment_method_types[0]` sólo de respaldo (medido el
    13-10-2026: Checkout deja el PI con un solo tipo, el usado)."""
    pi = sesion.get("payment_intent")
    if not isinstance(pi, dict):
        return ""
    pm = pi.get("payment_method")
    if isinstance(pm, dict) and pm.get("type"):
        return pm["type"]
    tipos = pi.get("payment_method_types") or []
    return tipos[0] if tipos else ""


def acreditar_a_mano(fila, sesion: dict) -> None:
    """Para `manage.py acreditar_sesion`: acredita confiando en la fila
    congelada, salteando la comparación con lo que Stripe reporta. Quien lo
    corre ya miró los dos valores; `a_mano` entrega aunque la fila tenga una
    disputa (el comando lo pide con `--aunque-disputada`)."""
    cobro.acreditar(
        fila, pago_id=_payment_intent_id(sesion), monto_pagado=fila.precio_de_lista() - fila.descuento_centavos,
        moneda=fila.moneda, medio=_medio_de_pago(sesion), external_id=f"stripe:session:{fila.checkout_id}",
        a_mano=True,
    )


def _avisar_si_el_precio_no_lleva_el_impuesto_incluido(session_id, sesion, monto) -> None:
    """Un precio en `exclusive` cobra el impuesto ENCIMA de los US$ 29.

    No frena la compra —el comprador pagó de más, no de menos, y rechazarla
    sería cerrar la caja por una mala configuración nuestra—, pero tiene que
    verse: sin este log, un precio mal creado cobraría de más en silencio.
    """
    descuento = (sesion.get("total_details") or {}).get("amount_discount") or 0
    total = sesion.get("amount_total")
    if total is not None and total != monto - descuento:
        logger.warning(
            "sesión %s: el total (%s) no es el subtotal (%s) menos el descuento (%s). "
            "¿El precio quedó con tax_behavior=exclusive?",
            session_id, total, monto, descuento,
        )


class ReembolsoSinCompra(Exception):
    """No hay ninguna compra nuestra con ese `payment_intent`... todavía."""


def _reembolsar(refund: dict) -> None:
    """Adaptador: resuelve la fila por `payment_intent` y delega en
    `cobro.reembolsar`, que es el mismo camino que usa Mercado Pago.

    El `external_id` lleva el prefijo `stripe:refund:` y no `stripe:session:`:
    con la misma clave que el pago, el reembolso se descartaría como duplicado
    de la compra que lo precedió. Es a la vez la constancia (`Reembolso`) y la
    clave del ledger; la 0065 prefijó los ids crudos que se guardaron antes.
    """
    refund_id = refund.get("id") or ""
    if not refund_id:
        # Sin id no hay constancia posible: el primero se guardaría con "" y
        # todos los siguientes sin id se darían por aplicados.
        logger.error("reembolso sin id (pi=%s): no se aplica", refund.get("payment_intent"))
        return
    payment_intent = refund.get("payment_intent") or ""
    if not payment_intent:
        # Sin `payment_intent` no hay forma de atribuir el reembolso, y buscar
        # por vacío engancharía cualquier compra abierta y todavía sin
        # acreditar: revocaría la de cualquiera. Reintentar no lo arregla.
        logger.error("reembolso %s sin payment_intent: no se revoca", refund_id)
        return

    fila = PasarelaCheckout.objects.filter(pasarela=PasarelaCheckout.STRIPE, pago_id=payment_intent).first()
    if fila is None:
        # ESTE sí se arregla reintentando: el reembolso puede llegar antes de
        # que la entrega del pago haya guardado el `payment_intent`. Es el
        # único "no encuentro la compra" que merece 5xx.
        raise ReembolsoSinCompra(
            f"reembolso {refund_id}: ninguna compra con payment_intent {payment_intent}",
        )

    # El contador de reembolsos suma también con los que emite Stripe por su
    # cuenta —Managed Payments los emite sin nuestra aprobación—: decidido el
    # 03-09-2026, porque el payload no dice quién inició el reembolso.
    cobro.reembolsar(
        fila, pago_id=payment_intent, refund_id=refund_id, monto=refund.get("amount") or 0,
        moneda=refund.get("currency") or "", external_id=f"stripe:refund:{refund_id}",
    )
