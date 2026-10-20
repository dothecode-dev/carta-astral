"""Acredita a mano una sesión de Stripe que el webhook no acreditó.

El webhook rechaza —con 200 y un `error` en el log— cuando lo que Stripe
reporta no cierra contra la fila que congelamos al abrir el checkout: otro
descuento, otro promotion code, otro subtotal. Reintentar no lo arregla y la
persona ya pagó. Esto es el procedimiento: se mira qué dice cada lado, y con
`--si-estoy-seguro` se acredita confiando en la fila. Deja todo lo que deja el
webhook —derecho, `acreditado_at`, constancia del cupón, mail, evento, informe
arrancado— y es idempotente por el `external_id` de la sesión.

Los montos se muestran con su moneda: 14900 contra 14900 no dicen nada si uno
es `brl` y el otro `usd`. Una fila con disputa no se acredita sin
`--aunque-disputada`: esos fondos ya se los llevó Stripe, y entregar encima es
regalar el producto.
"""
from django.core.management.base import BaseCommand, CommandError

from api import cobro, compra_anonima, webhooks_stripe
from api.models import PasarelaCheckout


class Command(BaseCommand):
    help = "Acredita a mano una sesión de Stripe que el webhook rechazó."

    def add_arguments(self, parser):
        parser.add_argument("session_id")
        parser.add_argument("--si-estoy-seguro", action="store_true", dest="confirmado")
        parser.add_argument("--aunque-disputada", action="store_true", dest="aunque_disputada")

    def handle(self, *args, **opts):
        session_id = opts["session_id"]
        fila = PasarelaCheckout.objects.filter(checkout_id=session_id).select_related("cupon", "account").first()
        # Una compra sin cuenta todavía no tiene cuenta si el webhook la
        # rechazó: `cobro` la adjudica por `mail_comprador` al acreditar.
        sin_cuenta_adjudicable = fila is not None and fila.anonimo and bool(fila.mail_comprador)
        if fila is None or (fila.account is None and not sin_cuenta_adjudicable):
            raise CommandError(f"no hay ningún checkout nuestro con cuenta para {session_id}")

        sesion = webhooks_stripe.obtener_sesion(session_id)
        total = sesion.get("total_details") or {}
        promos = [d.get("promotion_code") for d in (sesion.get("discounts") or [])]
        quien = fila.account_id or f"(sin cuenta: se adjudica a {compra_anonima.enmascarar(fila.mail_comprador)})"
        self.stdout.write(f"cuenta {quien} · {fila.codigo_producto} · payment_status={sesion.get('payment_status')}")
        self.stdout.write(
            f"  fila:   cupón={fila.cupon.codigo if fila.cupon else '—'} "
            f"promo={fila.cupon.stripe_promotion_code_id if fila.cupon else '—'} "
            f"descuento={fila.descuento_centavos} {fila.moneda} lista={fila.precio_de_lista()} {fila.moneda}"
        )
        moneda_sesion = (sesion.get("currency") or "?").lower()
        self.stdout.write(
            f"  stripe: promos={promos} amount_discount={total.get('amount_discount')} {moneda_sesion} "
            f"subtotal={sesion.get('amount_subtotal')} {moneda_sesion} "
            f"total={sesion.get('amount_total')} {moneda_sesion}"
        )
        if fila.disputa_id:
            self.stdout.write(self.style.ERROR(f"⚠️ fila DISPUTADA: {fila.disputa_id}"))
        if not opts["confirmado"]:
            self.stdout.write("Sin --si-estoy-seguro no se acreditó nada.")
            return
        if fila.disputa_id and not opts["aunque_disputada"]:
            raise CommandError(
                f"la fila tiene la disputa {fila.disputa_id}: sin --aunque-disputada no se acredita",
            )
        if sesion.get("payment_status") != "paid":
            raise CommandError("la sesión no está pagada: no se acredita")

        try:
            acreditada = webhooks_stripe.acreditar_a_mano(fila, sesion)
        except cobro.PagoDuplicado as exc:
            raise CommandError(
                f"no se acreditó: la compra ya la acreditó el pago {exc.acreditado_por} y {exc.pago_id} "
                "es un duplicado. Reembolsalo desde el dashboard de Stripe.",
            ) from exc
        except cobro.CompraDisputada as exc:
            raise CommandError(
                f"no se acreditó: la fila tiene la disputa {exc}. Con --aunque-disputada se entrega igual.",
            ) from exc
        if acreditada:
            self.stdout.write(self.style.SUCCESS(f"acreditada {session_id} con descuento {fila.descuento_centavos}"))
            return
        # `cobro` devuelve False también para la repetición de una compra ya
        # acreditada: eso no es un error, el comando es idempotente.
        fila.refresh_from_db(fields=["acreditado_at", "pago_id"])
        pago_id = webhooks_stripe._payment_intent_id(sesion)
        if fila.acreditado_at is not None and pago_id and fila.pago_id == pago_id:
            self.stdout.write(f"{session_id} ya estaba acreditada por el pago {pago_id}: no se hizo nada.")
            return
        raise CommandError(
            f"no se acreditó {session_id}: el cobro la rechazó (sin id de pago, sin cuenta o un monto que "
            "no cierra). El motivo está en el log y en el aviso de Telegram.",
        )
