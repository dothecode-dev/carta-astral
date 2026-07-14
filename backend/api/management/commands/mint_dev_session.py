"""Crea (o reutiliza) una cuenta de desarrollo y emite un token de sesión.

SOLO para desarrollo local: la app móvil usa este token como si viniera del
SSO, sin pasar por Apple/Google. Con DEBUG apagado se niega a correr.

Uso:
    DEBUG=1 python manage.py mint_dev_session [--credits N]
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.auth import create_session
from api.models import Account


class Command(BaseCommand):
    help = "Emite un token de sesión para una cuenta de desarrollo (solo DEBUG)."

    def add_arguments(self, parser):
        parser.add_argument("--credits", type=int, default=10, help="créditos free iniciales")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("mint_dev_session solo funciona con DEBUG=1")

        account, created = Account.objects.get_or_create(
            email="dev@localhost",
            defaults={"free_balance": options["credits"], "paid_balance": 0},
        )
        token = create_session(account)
        state = "creada" if created else "reutilizada"
        self.stdout.write(f"cuenta {state}: id={account.id} email={account.email}")
        self.stdout.write(f"token: {token}")
