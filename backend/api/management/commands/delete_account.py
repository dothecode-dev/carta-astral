from django.core.management.base import BaseCommand, CommandError
from api.deletion import delete_account
from api.models import Account


class Command(BaseCommand):
    help = "Borra una cuenta (datos personales) y deja el tombstone del free-tier."

    def add_arguments(self, parser):
        parser.add_argument("account_id", type=int)

    def handle(self, *args, **opts):
        account = Account.objects.filter(id=opts["account_id"]).first()
        if account is None:
            raise CommandError(f"cuenta {opts['account_id']} no existe")
        delete_account(account)
        self.stdout.write(self.style.SUCCESS(f"cuenta {opts['account_id']} borrada"))
