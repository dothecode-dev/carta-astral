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

from django.db import IntegrityError, transaction

from api import analitica, catalogo, compra_anonima, devoluciones, disputas, notificaciones
from api.avisos import avisar_admin
from api.canje import MontoInvalido, aplicar_compra
from api.compra_service import arrancar_informe
from api.models import Account, CuponUso, MailBloqueado, PasarelaCheckout, Reembolso
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


class SesionAnonimaSinEmail(Exception):
    """Una compra sin cuenta pagada sin mail: no hay a quién acreditarla."""


def _adjudicar_si_es_anonima(session_id: str, sesion: dict) -> None:
    """Le pone cuenta a una compra abierta sin cuenta, por el mail del pago
    (RF5), ANTES de todo lo que registra la compra contra la cuenta: el
    canje, el uso del cupón y la telemetría salen todos con ésta."""
    fila = PasarelaCheckout.objects.filter(checkout_id=session_id).only("anonimo", "account_id").first()
    if fila is None or not fila.anonimo or fila.account_id is not None:
        return
    email = ((sesion.get("customer_details") or {}).get("email") or "").strip()
    if not email:
        # Stripe siempre pide el mail (verificado en sandbox con Managed
        # Payments, 07-10-2026). Si falta es transitorio o un cambio de
        # Stripe: se pide el reintento en vez de perder la compra (RF7). La
        # vista lo loguea con nivel error y responde 5xx.
        raise SesionAnonimaSinEmail(f"sesión anónima {session_id} pagada sin email")
    compra_anonima.adjudicar(session_id, email)
    if MailBloqueado.bloqueado(email):
        # R8: la plata entró, se entrega igual; pero se mira.
        logger.warning("sesión %s: compra sin cuenta de un mail bloqueado; se acredita igual", session_id)
        # Enmascarado: el texto va a Telegram y, sin token, al log.
        avisar_admin(
            f"Stripe {session_id}: compra sin cuenta de un mail BLOQUEADO "
            f"({compra_anonima.enmascarar(email)}). Se acredita igual.",
        )


def _product_de(sesion: dict) -> str:
    """El Product de Stripe del único line item. Con `price_data` Stripe crea
    un Price efímero por sesión: su id no dice nada, el Product sí."""
    items = ((sesion.get("line_items") or {}).get("data")) or []
    if not items:
        return ""
    return ((items[0].get("price") or {}).get("product")) or ""


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

    # Antes de validar precio, producto y monto, y a propósito: si alguno de
    # esos falla, la entrega responde 200 sin acreditar, pero la cuenta ya
    # quedó creada (con su regalo de bienvenida) y la fila con cuenta. Es lo
    # que deja resolverlos a mano con `manage.py acreditar_sesion`, que
    # acredita sobre `fila.account`: sin cuenta en la fila no tendría a quién.
    _adjudicar_si_es_anonima(session_id, sesion)

    cuenta, fila = _resolver_cuenta_y_fila(sesion)
    if cuenta is None:
        logger.error("sesión %s sin cuenta que la reclame: no se acredita", session_id)
        avisar_admin(f"Stripe {session_id}: pagada y sin cuenta que la reclame. No se acreditó.")
        return

    if fila is not None and fila.disputa_id:
        # EC16: la disputa llegó antes que el pago. Esos fondos ya se los
        # llevó Stripe: entregar ahora sería regalar lo disputado.
        logger.error("sesión %s con disputa %s: no se entrega", session_id, fila.disputa_id)
        avisar_admin(
            f"Stripe {session_id}: llegó el pago de una compra ya disputada ({fila.disputa_id}). No se entregó.",
        )
        return

    # El Product de la sesión dice qué cobró Stripe; la fila dice qué abrimos.
    # Los dos tienen que coincidir: elegir uno solo es entregar de más o de menos.
    product_id = _product_de(sesion)
    try:
        codigo_sesion = codigo_de_product(product_id)
    except KeyError:
        logger.error("sesión %s con un Product que no mapeamos (%s): no se acredita", session_id, product_id)
        avisar_admin(f"Stripe {session_id}: Product {product_id} no está en STRIPE_PRODUCTOS. No se acreditó.")
        return
    if fila is not None and fila.codigo_producto != codigo_sesion:
        logger.error(
            "sesión %s: el checkout era de %s y la sesión dice %s", session_id, fila.codigo_producto, codigo_sesion,
        )
        avisar_admin(
            f"Stripe {session_id}: la fila es de {fila.codigo_producto} y la sesión trae {product_id} "
            f"({codigo_sesion}). No se acreditó.",
        )
        return
    codigo = fila.codigo_producto if fila is not None else codigo_sesion

    # La moneda de la sesión tiene que ser la congelada: 14900 centavos de
    # dólar no son 14900 de real, y `aplicar_compra` sólo compara enteros.
    # Sin fila sólo se acepta la base, que es la única con la que el catálogo
    # puede comparar (RF10).
    moneda_sesion = (sesion.get("currency") or "").lower()
    moneda_fila = fila.moneda if fila is not None else "usd"
    if moneda_sesion != moneda_fila:
        logger.error(
            "sesión %s en %s y la fila en %s: no se acredita", session_id, moneda_sesion, moneda_fila,
        )
        avisar_admin(
            f"Stripe {session_id}: la sesión vino en {moneda_sesion} y la fila está en {moneda_fila} "
            f"(subtotal {sesion.get('amount_subtotal')}). No se acreditó.",
        )
        return

    if fila is not None and fila.vencido_at is not None and fila.acreditado_at is None:
        # EC15: un Pix pagado después de que la sesión venció. La plata entró
        # y manda; se entrega, y se mira por qué llegó tarde.
        logger.warning("sesión %s pagada sobre una fila vencida: se acredita igual", session_id)
        avisar_admin(f"Stripe {session_id}: pago sobre una fila vencida; se acreditó igual.")

    monto = sesion.get("amount_subtotal")
    if monto is None:
        # `aplicar_compra` levantaría `MontoInvalido` con un `None != 2900` que
        # se lee como "el monto no coincide", que es otro problema con otro
        # arreglo. Se rechaza acá, con su propio log.
        logger.error("sesión %s sin monto (amount_subtotal nulo): no se acredita", session_id)
        avisar_admin(f"Stripe {session_id}: sin amount_subtotal. No se acreditó.")
        return

    _avisar_si_el_precio_no_lleva_el_impuesto_incluido(session_id, sesion, monto)

    try:
        descuento, cupon = _descuento_de(session_id, sesion, fila)
    except DescuentoNoCierra:
        # Ya logueado con los tres valores. Reintentar no lo arregla: lo
        # resuelve a mano `manage.py acreditar_sesion`.
        return

    _entregar(session_id, sesion, cuenta, fila, codigo, monto, descuento, cupon)


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
            avisar_admin(
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
        avisar_admin(
            f"Stripe {session_id}: el descuento no cierra (promos={promos}, reportado={reportado}). "
            "No se acreditó.",
        )
        raise DescuentoNoCierra
    return esperado, cupon


class CompraDisputada(Exception):
    """La fila tiene una disputa: esos fondos ya se los llevó Stripe."""


def _entregar(session_id, sesion, cuenta, fila, codigo, monto, descuento, cupon, a_mano=False) -> None:
    """Otorga, marca la fila, deja constancia del cupón, avisa, mide y arranca
    el informe. Lo comparten el webhook y `acreditar_sesion` (`a_mano`, que
    entrega aunque la fila tenga disputa: quien lo corre ya miró)."""
    external_id = f"stripe:session:{session_id}"
    pagado = monto - descuento
    try:
        aplicado = _otorgar_y_marcar(sesion, cuenta, fila, codigo, pagado, descuento, external_id, a_mano)
    except MontoInvalido:
        # Ya lo logueó `aplicar_compra` con los dos montos: acá no se repite.
        # Reintentar no lo arregla, así que la entrega se da por buena.
        avisar_admin(
            f"Stripe {session_id}: el monto no coincide (pagado {pagado} {fila.moneda if fila else 'usd'}, "
            f"lista {fila.precio_de_lista() if fila else '?'}). No se acreditó.",
        )
        return
    except CompraDisputada as e:
        logger.error("sesión %s con disputa %s: no se entrega", session_id, e)
        avisar_admin(f"Stripe {session_id}: llegó el pago de una compra ya disputada ({e}). No se entregó.")
        return

    if cupon is not None:
        _registrar_uso(cupon, cuenta, fila, codigo, descuento, pagado, external_id)

    # En el idioma en que compró, no en español siempre: el locale queda
    # guardado al abrir el checkout. Sin `fila` no hay de dónde sacarlo
    # —una sesión que Stripe reporta y nosotros no registramos— y ahí sí
    # cae el default.
    lang = fila.locale if fila is not None else "es"
    if aplicado:
        logger.info("sesión %s acreditada: %s", session_id, codigo)
        # Acá y no en el navegador: quien paga cierra la pestaña —el informe
        # tarda seis minutos— y esa compra no la mediría nadie. Dentro del
        # mismo `if aplicado`, que es lo que ya hace idempotente al aviso: un
        # reintento de Stripe no puede contar la compra dos veces. El monto es
        # LO PAGADO, no la lista: con cupón, la lista sería un ingreso mentira.
        analitica.evento(
            cuenta, "compra_completada",
            {
                "producto": codigo, "monto_centavos": pagado, "locale": lang,
                "cupon": cupon.codigo if cupon is not None else None,
                "moneda": fila.moneda if fila is not None else "usd",
            },
        )

    # Sin `try`: si el informe no arranca, la excepción sube y la vista pide el
    # reintento. Única excepción: `arrancar_informe` absorbe `SinDerecho` cuando
    # la unidad comprada saldó una deuda (RF5b) y el rastro lo confirma; ahí no
    # hay informe que escribir y reintentar no lo arregla. La plata ya está acreditada —los requests no corren en
    # transacción y el átomo de `aplicar_compra` cerró antes— y el arranque es
    # idempotente (`iniciar_generacion` usa `get_or_create`), así que el
    # reintento lo único que hace es volver a intentar lo que falló. Con Polar
    # esto se tragaba el error por obligación: allá diez fallidas seguidas
    # deshabilitan el endpoint para todos.
    informe_en_curso = False
    try:
        informe_en_curso = arrancar_informe(cuenta, fila)
    finally:
        # Un solo aviso por compra, y sólo en la entrega que la acreditó: en
        # un reintento la compra ya se acreditó y avisar de nuevo sería un
        # segundo mail. Va después del arranque porque es lo que dice cuál
        # mandar: «lo estamos escribiendo» sólo si de verdad quedó un informe
        # escribiéndose; si no —un pack, una deuda saldada o un arranque que
        # falló y queda para el reintento—, el genérico, que siempre es cierto.
        # `notificar` no lanza, así que no tapa la excepción del arranque.
        if aplicado:
            evento = "informe_en_curso" if informe_en_curso else "compra_acreditada"
            notificaciones.notificar(
                cuenta, evento, {"producto": codigo, "medio": _medio_de_pago(sesion)}, lang=lang,
            )


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


def _otorgar_y_marcar(sesion, cuenta, fila, codigo, pagado, descuento, external_id, a_mano) -> bool:
    """Otorga y marca la fila acreditada en UN átomo, con la fila bloqueada.

    La disputa se vuelve a mirar acá: una que se procesó entre el chequeo de
    `_acreditar` y este punto no se pierde. `_retirar_por_disputa` bloquea la
    misma fila, así que o ve `acreditado_at` puesto y revoca, o deja la marca
    y acá no se entrega.
    """
    with transaction.atomic():
        if fila is not None:
            bloqueada = PasarelaCheckout.objects.select_for_update().only("disputa_id").get(pk=fila.pk)
            if bloqueada.disputa_id and not a_mano:
                raise CompraDisputada(bloqueada.disputa_id)
        # `amount_subtotal` y no `amount_total`: MEDIDO el 03-09-2026 contra una
        # sesión pagada de verdad con dirección española. Con Managed Payments
        # el subtotal NO baja —los dos campos llegan en el precio de lista y el
        # impuesto va aparte, en `total_details`—, así que el subtotal vale el
        # precio de lista en la moneda de la sesión con impuesto incluido y
        # también con impuesto encima. `amount_total` sólo coincide con el
        # catálogo mientras el precio esté en `inclusive`. Con cupón (medido el
        # 06-09-2026) tampoco baja: el descuento va en
        # `total_details.amount_discount`, y acá se resta el congelado.
        aplicado = aplicar_compra(
            cuenta, codigo, pagado,
            external_id=external_id,
            sujeto=fila.sujeto if fila is not None else None,
            descuento_centavos=descuento,
            precio_centavos=fila.precio_de_lista() if fila is not None else None,
            al_saldar_deuda=(lambda: _marcar_saldo_deuda(fila)) if fila is not None else None,
        )
        if fila is not None:
            # Fuera del `if aplicado`: en un reintento posterior a un fallo
            # tardío, `aplicar_compra` devuelve False porque el external_id ya
            # está aplicado y la compra YA fue entregada. Si la marca dependiera
            # de ese True, la página de retorno diría "pendiente" para siempre
            # sobre un informe que la persona ya tiene.
            fila.payment_intent = _payment_intent_id(sesion)
            fila.acreditado_at = fila.acreditado_at or timezone.now()
            fila.save(update_fields=["payment_intent", "acreditado_at"])
    return aplicado


def _marcar_saldo_deuda(fila) -> None:
    """RF5b: la compra saldó deuda y no hay informe. Corre dentro del átomo de
    `aplicar_compra`, antes de que la fila se marque acreditada: quien sondea
    el estado nunca ve «acreditado» sin el aviso."""
    PasarelaCheckout.objects.filter(pk=fila.pk).update(saldo_deuda=True)
    fila.saldo_deuda = True


def _registrar_uso(cupon, cuenta, fila, codigo, descuento, pagado, external_id) -> None:
    """La constancia del cupón, FUERA del átomo de la compra y sin poder
    revertirla: un fallo acá se loguea y la persona se queda con lo que pagó.
    Idempotente por `external_id`, así `completed` y `async_payment_succeeded`
    de la misma sesión cuentan un solo uso."""
    try:
        CuponUso.objects.get_or_create(
            external_id=external_id,
            defaults=dict(
                cupon=cupon, account=cuenta, codigo_producto=codigo, checkout=fila,
                descuento_centavos=descuento, monto_pagado_centavos=pagado,
                moneda=fila.moneda if fila is not None else "usd",
            ),
        )
    except IntegrityError:
        logger.exception(
            "no se pudo registrar el uso del cupón %s en %s; la compra queda acreditada igual",
            cupon.codigo, external_id,
        )


def acreditar_a_mano(fila, sesion: dict) -> None:
    """Para `manage.py acreditar_sesion`: acredita confiando en la fila
    congelada, salteando la comparación con lo que Stripe reporta. Quien lo
    corre ya miró los dos valores."""
    codigo = fila.codigo_producto
    precio = fila.precio_de_lista()
    _entregar(
        fila.checkout_id, sesion, fila.account, fila, codigo,
        precio, fila.descuento_centavos, fila.cupon if fila.descuento_centavos else None,
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
    """Revoca lo comprado y anota como deuda lo que ya se usó.

    Nunca se le quita a nadie un informe entregado: `canje.revocar` baja el
    derecho hasta donde alcanza y el resto queda como deuda, que se cancela
    contra la próxima compra.

    El `external_id` lleva el prefijo `stripe:refund:` y no `stripe:session:`:
    con la misma clave que el pago, el reembolso se descartaría como duplicado
    de la compra que lo precedió.
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

    fila = PasarelaCheckout.objects.filter(payment_intent=payment_intent).first()
    if fila is None:
        # ESTE sí se arregla reintentando: el reembolso puede llegar antes de
        # que la entrega del pago haya guardado el `payment_intent`. Es el
        # único "no encuentro la compra" que merece 5xx.
        raise ReembolsoSinCompra(
            f"reembolso {refund_id}: ninguna compra con payment_intent {payment_intent}",
        )

    # Los montos sólo se comparan en la moneda de la compra: un reembolso de
    # 2900 `brl` sobre una compra en `usd` no son 2900 de nada.
    moneda_refund = (refund.get("currency") or "").lower()
    if moneda_refund != fila.moneda:
        logger.error(
            "reembolso %s en %s sobre una compra en %s: no se revoca", refund_id, moneda_refund, fila.moneda,
        )
        avisar_admin(
            f"Stripe refund {refund_id}: vino en {moneda_refund} y la compra {fila.checkout_id} está en "
            f"{fila.moneda}. No se revocó nada.",
        )
        return

    # `fila.account` puede ser None si la cuenta se borró después de comprar
    # (RF22): `revocar` lo contempla y registra el movimiento igual, para que
    # la contabilidad cierre aunque no haya a quién cobrarle la deuda.
    #
    # El contador de reembolsos suma también con los que emite Stripe por su
    # cuenta —Managed Payments los emite sin nuestra aprobación—: decidido el
    # 03-09-2026, porque el payload no dice quién inició el reembolso y
    # `flagged` no bloquea nada, sólo marca la cuenta para mirarla.
    monto = refund.get("amount") or 0
    with transaction.atomic():
        # Bloqueada: la cuenta de unidades lee `unidades_revocadas` y la
        # actualiza, y dos reembolsos (o un reembolso y una disputa) pueden
        # llegar a la vez. `of=("self",)`: `account` es nullable.
        fila = PasarelaCheckout.objects.select_for_update(of=("self",)).select_related("account").get(pk=fila.pk)
        # La constancia es `Reembolso` (la 0059 la completó para los
        # reembolsos aplicados antes de que existiera).
        if Reembolso.objects.filter(refund_id=refund_id).exists():
            logger.info("reembolso %s ya aplicado", refund_id)
            return
        prod = catalogo.producto(fila.codigo_producto)
        # Sobre LO PAGADO, no sobre la lista: un pack de 5 al 50 % (paga 6250)
        # reembolsado entero caía en la rama parcial y revocaba 3. Con un
        # regalo del 100 % lo pagado es 0: cualquier reembolso es total.
        base = devoluciones.pagado(fila)
        if not devoluciones.cubre_todo(fila, monto) and len(prod.otorga) != 1:
            # Un combo devuelto a medias no tiene una respuesta obvia —¿qué
            # mitad de "carta + horóscopo" se revoca?— y hoy no existe ninguno
            # en el catálogo. No se revoca nada, pero el monto se anota y queda
            # la constancia: una disputa posterior no lo cuenta como no devuelto.
            Reembolso.objects.create(refund_id=refund_id, fila=fila, monto=monto)
            devoluciones.registrar(fila, 0, monto)
            logger.error("reembolso %s parcial sobre el combo %s: no se revoca", refund_id, fila.codigo_producto)
            aviso = (
                f"Stripe refund {refund_id}: parcial ({monto} {fila.moneda}) sobre el combo "
                f"{fila.codigo_producto} {fila.checkout_id}. No se revocó nada: resolver a mano."
            )
        else:
            aviso = None
            # Proporción redondeada HACIA ARRIBA (decidido el 03-09-2026) y
            # nunca más de lo que queda sin revocar: la suma de varios
            # parciales redondeados no puede pasarse de lo que el pack dio. Lo
            # que no queda puede tenerlo una disputa abierta (ver
            # `tomar_de_disputa`).
            pedidas = devoluciones.unidades_pedidas(fila, monto)
            unidades = min(pedidas, devoluciones.quedan(fila))
            if unidades and devoluciones.revocar_unidades(fila, unidades, f"stripe:refund:{refund_id}") is None:
                logger.info("reembolso %s ya revocado en el ledger", refund_id)
                return
            tomadas, cedido = disputas.ceder_a_reembolso(fila, pedidas - unidades, monto)
            Reembolso.objects.create(refund_id=refund_id, fila=fila, monto=monto, unidades=unidades + tomadas)
            # Lo que la disputa ya había anotado de este monto no se suma dos veces.
            devoluciones.registrar(fila, unidades, monto - cedido)
            logger.info(
                "reembolso %s (%s de %s): revocadas %s unidades de %s, %s tomadas de una disputa",
                refund_id, monto, base, unidades, fila.codigo_producto, tomadas,
            )
    if aviso:
        avisar_admin(aviso)
