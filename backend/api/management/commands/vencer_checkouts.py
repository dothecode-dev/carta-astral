"""Vence los checkouts de Mercado Pago que nunca se pagaron (RF13).

Una preferencia de MP no avisa cuando vence, y si el backend estuvo caído
cuando llegó un pago, MP no reintenta tarde: este comando, que busca los pagos
por `external_reference`, es la red de seguridad. Lo dispara una Scheduled Task
de Coolify cada 15 minutos; la lógica vive en `pasarelas.mercadopago.revisar_vencidas`.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.pasarelas import mercadopago


class Command(BaseCommand):
    help = "Revisa los checkouts de Mercado Pago pasada su vida: acredita, reembolsa duplicados, vence o descarta."

    def handle(self, *args, **options):
        self.stdout.write(str(mercadopago.revisar_vencidas(timezone.now())))
