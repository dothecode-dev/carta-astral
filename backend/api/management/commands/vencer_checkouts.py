"""Vence los checkouts de Mercado Pago que nunca se pagaron (RF13).

Una preferencia de MP no avisa cuando vence, y si el backend estuvo caído
cuando llegó un pago, MP no reintenta tarde: este comando, que busca los pagos
por `external_reference`, es la red de seguridad; y concilia los pagos que MP
modificó en las últimas horas (`conciliar_actualizados`). Lo dispara una Scheduled Task
de Coolify cada 15 minutos; la lógica vive en `pasarelas.mercadopago.revisar_vencidas`.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.pasarelas import mercadopago


class Command(BaseCommand):
    help = (
        "Revisa los checkouts de Mercado Pago pasada su vida (acredita, reembolsa duplicados, vence o descarta) "
        "y concilia los pagos modificados en las últimas horas."
    )

    def handle(self, *args, **options):
        ahora = timezone.now()
        self.stdout.write(str(mercadopago.revisar_vencidas(ahora)))
        # Ruling 15: después de revisar las filas vencidas, los pagos que MP
        # modificó hace poco (reembolsos y cambios de estado cuya notificación
        # se perdió).
        self.stdout.write(str(mercadopago.conciliar_actualizados(ahora)))
