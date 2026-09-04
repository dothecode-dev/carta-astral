"""El webhook de Stripe: por acá entra la plata.

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

from api import analitica, catalogo, notificaciones
from api.canje import MontoInvalido, aplicar_compra, revocar
from api.compra_service import arrancar_informe
from api.models import Account, PasarelaCheckout
from api.stripe_client import FirmaInvalida, codigo_de_producto, obtener_sesion, verificar_firma

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
        if tipo not in EVENTOS_PAGO + EVENTOS_REEMBOLSO:
            logger.info("evento de stripe ignorado: %s", tipo)
            return Response(status=status.HTTP_200_OK)

        try:
            if tipo in EVENTOS_PAGO:
                _acreditar(objeto.get("id", ""))
            else:
                _reembolsar(objeto)
        except Exception:
            # Transitorio hasta que se demuestre lo contrario: se pide el
            # reintento en vez de perder la operación. Lo definitivo ya salió
            # por `return` adentro de cada función.
            logger.exception("entrega de stripe %s fallida: se pide reintento", tipo)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(status=status.HTTP_200_OK)


def _resolver_cuenta_y_fila(sesion: dict):
    """A quién le corresponde esta compra, y con qué carta si vino de una.

    Manda nuestra fila: además de la cuenta guarda la carta y el idioma, que la
    pasarela no conoce. La metadata queda como respaldo para una sesión que se
    haya creado fuera del flujo normal.
    """
    fila = PasarelaCheckout.objects.filter(checkout_id=sesion.get("id", "")).first()
    if fila is not None and fila.account is not None:
        return fila.account, fila

    account_id = (sesion.get("metadata") or {}).get("account_id")
    if account_id:
        cuenta = Account.objects.filter(pk=account_id).first()
        if cuenta is not None:
            return cuenta, fila
    return None, fila


def _precio_de(sesion: dict) -> str:
    items = ((sesion.get("line_items") or {}).get("data")) or []
    if not items:
        return ""
    return ((items[0].get("price") or {}).get("id")) or ""


def _acreditar(session_id: str) -> None:
    """Traduce una sesión pagada en derechos.

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

    cuenta, fila = _resolver_cuenta_y_fila(sesion)
    if cuenta is None:
        logger.error("sesión %s sin cuenta que la reclame: no se acredita", session_id)
        return

    try:
        codigo = codigo_de_producto(_precio_de(sesion))
    except KeyError:
        logger.error("sesión %s con un precio que no mapeamos: no se acredita", session_id)
        return

    if fila is not None and fila.codigo_producto != codigo:
        # El checkout se abrió para un producto y la sesión dice otro. No es un
        # caso que sepamos resolver, y elegir mal significa entregar de más o
        # de menos: se registra y no se acredita.
        logger.error(
            "sesión %s: el checkout era de %s y la sesión dice %s",
            session_id, fila.codigo_producto, codigo,
        )
        return

    monto = sesion.get("amount_subtotal")
    if monto is None:
        # `aplicar_compra` levantaría `MontoInvalido` con un `None != 2900` que
        # se lee como "el monto no coincide", que es otro problema con otro
        # arreglo. Se rechaza acá, con su propio log.
        logger.error("sesión %s sin monto (amount_subtotal nulo): no se acredita", session_id)
        return

    _avisar_si_el_precio_no_lleva_el_impuesto_incluido(session_id, sesion, monto)

    try:
        # `amount_subtotal` y no `amount_total`: MEDIDO el 03-09-2026 contra una
        # sesión pagada de verdad con dirección española. Con Managed Payments
        # el subtotal NO baja —los dos campos llegan en el precio de lista y el
        # impuesto va aparte, en `total_details`—, así que el subtotal vale 2900
        # con impuesto incluido y también con impuesto encima. `amount_total`
        # sólo coincide con el catálogo mientras el precio esté en `inclusive`.
        aplicado = aplicar_compra(
            cuenta, codigo, monto,
            external_id=f"stripe:session:{session_id}",
            chart=fila.chart if fila is not None else None,
        )
    except MontoInvalido:
        # Ya lo logueó `aplicar_compra` con los dos montos: acá no se repite.
        # Reintentar no lo arregla, así que la entrega se da por buena.
        return

    if fila is not None:
        # Fuera del `if aplicado`: en un reintento posterior a un fallo tardío,
        # `aplicar_compra` devuelve False porque el external_id ya está aplicado
        # y la compra YA fue entregada. Si la marca dependiera de ese True, la
        # página de retorno diría "pendiente" para siempre sobre un informe que
        # la persona ya tiene.
        fila.payment_intent = sesion.get("payment_intent") or ""
        fila.acreditado_at = fila.acreditado_at or timezone.now()
        fila.save(update_fields=["payment_intent", "acreditado_at"])

    if aplicado:
        logger.info("sesión %s acreditada: %s", session_id, codigo)
        # Dentro del `if`: en un reintento la compra ya se acreditó y avisar de
        # nuevo sería un segundo mail por la misma compra.
        lang = fila.locale if fila is not None else "es"
        # En el idioma en que compró, no en español siempre: el locale queda
        # guardado al abrir el checkout. Sin `fila` no hay de dónde sacarlo
        # —una sesión que Stripe reporta y nosotros no registramos— y ahí sí
        # cae el default.
        notificaciones.notificar(cuenta, "compra_acreditada", {"producto": codigo}, lang=lang)
        # Acá y no en el navegador: quien paga cierra la pestaña —el informe
        # tarda seis minutos— y esa compra no la mediría nadie. Dentro del
        # mismo `if aplicado`, que es lo que ya hace idempotente al aviso: un
        # reintento de Stripe no puede contar la compra dos veces.
        analitica.evento(
            cuenta, "compra_completada",
            {"producto": codigo, "monto_centavos": monto, "locale": lang},
        )

    # Sin `try`: si el informe no arranca, la excepción sube y la vista pide el
    # reintento. La plata ya está acreditada —los requests no corren en
    # transacción y el átomo de `aplicar_compra` cerró antes— y el arranque es
    # idempotente (`iniciar_generacion` usa `get_or_create`), así que el
    # reintento lo único que hace es volver a intentar lo que falló. Con Polar
    # esto se tragaba el error por obligación: allá diez fallidas seguidas
    # deshabilitan el endpoint para todos.
    arrancar_informe(cuenta, fila)


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
    """Revoca lo comprado y anota como deuda lo que ya se usó.

    Nunca se le quita a nadie un informe entregado: `canje.revocar` baja el
    derecho hasta donde alcanza y el resto queda como deuda, que se cancela
    contra la próxima compra.

    El `external_id` lleva el prefijo `stripe:refund:` y no `stripe:session:`:
    con la misma clave que el pago, el reembolso se descartaría como duplicado
    de la compra que lo precedió.
    """
    refund_id = refund.get("id", "")
    payment_intent = refund.get("payment_intent") or ""
    if not payment_intent:
        # Sin `payment_intent` no hay forma de atribuir el reembolso, y buscar
        # por vacío engancharía cualquier compra abierta y todavía sin
        # acreditar: revocaría la de cualquiera. Reintentar no lo arregla.
        logger.error("reembolso %s sin payment_intent: no se revoca", refund_id)
        return

    fila = PasarelaCheckout.objects.filter(payment_intent=payment_intent).first()
    if fila is None:
        # ESTE sí se arregla reintentando: el reembolso puede llegar antes de
        # que la entrega del pago haya guardado el `payment_intent`. Es el
        # único "no encuentro la compra" que merece 5xx.
        raise ReembolsoSinCompra(
            f"reembolso {refund_id}: ninguna compra con payment_intent {payment_intent}",
        )

    # `fila.account` puede ser None si la cuenta se borró después de comprar
    # (RF22): `revocar` lo contempla y registra el movimiento igual, para que
    # la contabilidad cierre aunque no haya a quién cobrarle la deuda.
    #
    # El contador de reembolsos suma también con los que emite Stripe por su
    # cuenta —Managed Payments los emite sin nuestra aprobación—: decidido el
    # 03-09-2026, porque el payload no dice quién inició el reembolso y
    # `flagged` no bloquea nada, sólo marca la cuenta para mirarla.
    external_id = f"stripe:refund:{refund_id}"
    prod = catalogo.producto(fila.codigo_producto)
    monto = refund.get("amount") or 0

    if monto >= prod.precio_centavos:
        # Reembolso total: se revoca el producto COMPRADO, que es lo que deja
        # el Movimiento diciendo qué se reembolsó, y `revocar` traduce a lo que
        # ese producto otorgó.
        revocar(fila.account, fila.codigo_producto, 1, external_id=external_id)
        logger.info("reembolso %s revocado entero: %s", refund_id, fila.codigo_producto)
        return

    if len(prod.otorga) != 1:
        # Un combo devuelto a medias no tiene una respuesta obvia —¿qué mitad
        # de "carta + horóscopo" se revoca?— y hoy no existe ninguno en el
        # catálogo. Antes que inventar una regla, queda a la vista.
        logger.error(
            "reembolso %s parcial sobre un producto que otorga %s cosas (%s): "
            "no se revoca, resolver a mano",
            refund_id, len(prod.otorga), fila.codigo_producto,
        )
        return

    # Proporción redondeada HACIA ARRIBA (decidido el 03-09-2026): media
    # devolución de un pack de 5 revoca 3, y cualquier reembolso parcial de un
    # producto suelto revoca su única unidad, porque no existe medio informe.
    # Ante la duda no se regala producto; lo que ya se usó no se le saca a
    # nadie igual, eso va a deuda. En enteros, para no arrastrar floats.
    codigo_otorgado, multiplicador = prod.otorga[0]
    unidades = -(-monto * multiplicador // prod.precio_centavos)
    if unidades <= 0:
        logger.error("reembolso %s por %s: no alcanza a una unidad", refund_id, monto)
        return

    revocar(fila.account, codigo_otorgado, unidades, external_id=external_id)
    logger.info(
        "reembolso %s parcial (%s de %s): revocadas %s de %s unidades de %s",
        refund_id, monto, prod.precio_centavos, unidades, multiplicador, codigo_otorgado,
    )
