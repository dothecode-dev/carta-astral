from django.core.management.base import BaseCommand, CommandError

from api.ledger import grant_paid
from api.models import Account


class Command(BaseCommand):
    help = "Suma créditos pagados a una cuenta (recarga manual, sin IAP)."

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
        grant_paid(account, n, note="grant_credits CLI")
        self.stdout.write(self.style.SUCCESS(f"+{n} créditos a cuenta {opts['account_id']}"))
