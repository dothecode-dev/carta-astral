from django.core.management.base import BaseCommand
from django.utils import timezone
from api.models import Session


class Command(BaseCommand):
    help = "Borra sesiones expiradas."

    def handle(self, *args, **opts):
        deleted, _ = Session.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(self.style.SUCCESS(f"{deleted} sesiones expiradas borradas"))
