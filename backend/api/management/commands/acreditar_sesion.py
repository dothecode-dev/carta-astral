"""Acredita a mano una sesión de Stripe que el webhook no acreditó.

El webhook rechaza —con 200 y un `error` en el log— cuando lo que Stripe
reporta no cierra contra la fila que congelamos al abrir el checkout: otro
descuento, otro promotion code, otro subtotal. Reintentar no lo arregla y la
persona ya pagó. Esto es el procedimiento: se mira qué dice cada lado, y con
`--si-estoy-seguro` se acredita confiando en la fila. Deja todo lo que deja el
webhook —derecho, `acreditado_at`, constancia del cupón, mail, evento, informe
arrancado— y es idempotente por el `external_id` de la sesión.
"""
from django.core.management.base import BaseCommand, CommandError

from api import webhooks_stripe
from api.models import PasarelaCheckout


class Command(BaseCommand):
    help = "Acredita a mano una sesión de Stripe que el webhook rechazó."

    def add_arguments(self, parser):
        parser.add_argument("session_id")
        parser.add_argument("--si-estoy-seguro", action="store_true", dest="confirmado")

    def handle(self, *args, **opts):
        session_id = opts["session_id"]
        fila = PasarelaCheckout.objects.filter(checkout_id=session_id).select_related("cupon", "account").first()
        if fila is None or fila.account is None:
            raise CommandError(f"no hay ningún checkout nuestro con cuenta para {session_id}")

        sesion = webhooks_stripe.obtener_sesion(session_id)
        total = sesion.get("total_details") or {}
        promos = [d.get("promotion_code") for d in (sesion.get("discounts") or [])]
        self.stdout.write(f"cuenta {fila.account_id} · {fila.codigo_producto} · payment_status={sesion.get('payment_status')}")
        self.stdout.write(
            f"  fila:   cupón={fila.cupon.codigo if fila.cupon else '—'} "
            f"promo={fila.cupon.stripe_promotion_code_id if fila.cupon else '—'} "
            f"descuento={fila.descuento_centavos}"
        )
        self.stdout.write(
            f"  stripe: promos={promos} amount_discount={total.get('amount_discount')} "
            f"subtotal={sesion.get('amount_subtotal')} total={sesion.get('amount_total')}"
        )
        if not opts["confirmado"]:
            self.stdout.write("Sin --si-estoy-seguro no se acreditó nada.")
            return
        if sesion.get("payment_status") != "paid":
            raise CommandError("la sesión no está pagada: no se acredita")

        webhooks_stripe.acreditar_a_mano(fila, sesion)
        self.stdout.write(self.style.SUCCESS(f"acreditada {session_id} con descuento {fila.descuento_centavos}"))
