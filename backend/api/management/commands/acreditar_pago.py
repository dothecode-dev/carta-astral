"""Acredita a mano un pago de Mercado Pago que el webhook no acreditó.

Corre la misma traducción que el webhook (`mercadopago.procesar_pago`): lee el
pago de la API de MP y deja lo mismo que dejaría la notificación —derecho,
`acreditado_at`, mail, evento, informe arrancado—, con la misma idempotencia:
correrlo dos veces no acredita dos veces. Sirve cuando MP agotó sus reintentos
o cuando un 5xx nuestro (`FilaInexistente`, `CompraAnonimaSinMail`) ya se
arregló y la notificación no va a volver.

Para Stripe el procedimiento es otro: `acreditar_sesion`.
"""
from django.core.management.base import BaseCommand, CommandError

from api import cobro
from api.pasarelas import mercadopago, mercadopago_api


class Command(BaseCommand):
    help = "Acredita a mano un pago de Mercado Pago que el webhook no acreditó."

    def add_arguments(self, parser):
        parser.add_argument("--pasarela", required=True, choices=["mercadopago", "stripe"])
        parser.add_argument("payment_id")

    def handle(self, *args, **opts):
        if opts["pasarela"] == "stripe":
            raise CommandError("Para Stripe usá acreditar_sesion <session_id>.", returncode=2)
        payment_id = opts["payment_id"]
        if not mercadopago_api.id_valido(payment_id):
            raise CommandError(f"id de pago inválido: {payment_id!r}")
        try:
            mercadopago.procesar_pago(payment_id)
        except mercadopago_api.MPError as e:
            raise CommandError(f"Mercado Pago no devolvió el pago {payment_id}: {e}") from e
        except mercadopago.FilaInexistente as e:
            raise CommandError(
                f"el pago {payment_id} trae la referencia {e}, que no tiene fila nuestra: no se acreditó",
            ) from e
        except cobro.CompraAnonimaSinMail as e:
            raise CommandError(
                f"el pago {payment_id} es una compra sin cuenta y sin mail del comprador: "
                f"completá el mail en la fila y volvé a correrlo ({e})",
            ) from e
        self.stdout.write(self.style.SUCCESS(f"pago {payment_id} procesado"))
