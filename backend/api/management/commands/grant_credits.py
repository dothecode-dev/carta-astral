from django.core.management.base import BaseCommand, CommandError
from django.db.models import F

from api.models import Installation


class Command(BaseCommand):
    help = "Suma créditos comprados a una instalación (recarga manual, sin IAP)."

    def add_arguments(self, parser):
        parser.add_argument("installation_id", type=int)
        parser.add_argument("n", type=int)

    def handle(self, *args, **opts):
        n = opts["n"]
        if n <= 0:
            raise CommandError("n debe ser positivo")
        updated = Installation.objects.filter(id=opts["installation_id"]).update(
            purchased_credits=F("purchased_credits") + n
        )
        if not updated:
            raise CommandError(f"instalación {opts['installation_id']} no existe")
        self.stdout.write(self.style.SUCCESS(f"+{n} créditos a instalación {opts['installation_id']}"))
