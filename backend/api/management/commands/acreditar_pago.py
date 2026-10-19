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
from api.models import PasarelaCheckout
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
        except mercadopago_api.MPNoConfigurado as e:
            raise CommandError(
                "MP_ACCESS_TOKEN no está configurado en este entorno: no se pudo leer el pago ni acreditar nada",
            ) from e
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
        self._informar_resultado(payment_id)

    def _informar_desde_la_base(self, payment_id: str, error: Exception) -> None:
        fila = PasarelaCheckout.objects.filter(
            pasarela=PasarelaCheckout.MERCADOPAGO, payment_intent=payment_id, acreditado_at__isnull=False,
        ).first()
        if fila is not None:
            self.stdout.write(self.style.SUCCESS(
                f"pago {payment_id} acreditado ({fila.checkout_id}, acreditado_at={fila.acreditado_at.isoformat()}); "
                f"no se pudo releer el pago para confirmar su estado ({error}), el resultado sale de la base",
            ))
            return
        raise CommandError(
            f"el pago {payment_id} se procesó pero no quedó acreditado en ninguna compra, y no se pudo releer "
            f"de MP para saber su estado ({error}): revisar los avisos y el log",
        )

    def _informar_resultado(self, payment_id: str) -> None:
        """`procesar_pago` vuelve sin levantar tanto si acreditó como si no tenía
        nada que hacer: lo que pasó de verdad se lee de la fila, no se supone."""
        try:
            pago = mercadopago_api.obtener_pago(payment_id)
        except (mercadopago_api.MPError, mercadopago_api.MPNoConfigurado) as e:
            # `procesar_pago` ya corrió bien: la relectura sólo confirmaba. Lo
            # que quedó se lee de la base, no se convierte en un error falso.
            self._informar_desde_la_base(payment_id, e)
            return
        referencia = pago.get("external_reference") or ""
        estado = pago.get("status") or "?"
        fila = PasarelaCheckout.objects.filter(checkout_id=referencia).first() if referencia else None
        if fila is None:
            raise CommandError(
                f"el pago {payment_id} trae una referencia ajena ({referencia!r}): no es una compra nuestra, "
                "no se acreditó nada",
            )
        if fila.pasarela != PasarelaCheckout.MERCADOPAGO:
            raise CommandError(
                f"el pago {payment_id} apunta a {fila.checkout_id}, que es una compra de {fila.pasarela}: "
                "no se acreditó nada",
            )
        if fila.acreditado_at and fila.payment_intent == payment_id:
            self.stdout.write(self.style.SUCCESS(
                f"pago {payment_id} acreditado ({fila.checkout_id}, acreditado_at={fila.acreditado_at.isoformat()})",
            ))
            return
        if estado == "approved" and fila.acreditado_at:
            raise CommandError(
                f"duplicado: el pago {payment_id} no acreditó la compra {fila.checkout_id} "
                f"(ya la acreditó el pago {fila.payment_intent or '?'}; reembolso a verificar en MP y en el aviso de Telegram)",
            )
        if estado != "approved":
            raise CommandError(f"el pago {payment_id} está en status={estado}: no se acreditó nada")
        raise CommandError(
            f"el pago {payment_id} está aprobado pero la compra {fila.checkout_id} no quedó acreditada "
            "(¿disputada?): revisar los avisos y el log",
        )
