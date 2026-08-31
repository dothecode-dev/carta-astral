from uuid import uuid4

from django.core.management.base import BaseCommand, CommandError

from api.canje import otorgar
from api.models import Account


class Command(BaseCommand):
    help = "Otorga derechos de informe_natal a una cuenta (recarga manual, sin IAP)."

    def add_arguments(self, parser):
        parser.add_argument("account_id", type=int)
        parser.add_argument("n", type=int)

    def handle(self, *args, **opts):
        n = opts["n"]
        if n <= 0:
            raise CommandError("n debe ser positivo")
        account = Account.objects.filter(id=opts["account_id"]).first()
        if account is None:
            raise CommandError(f"cuenta {opts['account_id']} no existe")
        # external_id único por invocación: no es para idempotencia (este
        # comando nunca la tuvo, es aditivo a propósito — correrlo dos veces
        # es acreditar dos veces), sino para poder identificar cada recarga
        # manual en el admin y en la auditoría.
        otorgar(
            account, "informe_natal", n, origen="ajuste",
            external_id=f"cli:{uuid4()}", note="grant_credits CLI",
        )
        self.stdout.write(
            self.style.SUCCESS(f"+{n} informe_natal a cuenta {opts['account_id']}")
        )
