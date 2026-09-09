"""Borra los códigos de acceso por mail que ya no hacen falta (Hallazgo 5,
re-revisión de `puertas-de-acceso`).

El `pedir()` viejo marcaba `usado_en` en la fila vencida al reenviar; desde
que conviven varios códigos vigentes por dirección (Hallazgo I1) ninguna fila
se toca al vencer. Con hasta 5 filas vigentes por dirección y sin ninguna
constraint que las junte, se acumulan indefinidamente — incluso las de
direcciones que nunca llegaron a tener cuenta. Es una pregunta de retención
de PII (la dirección de mail), no de prolijidad.

Retención: 2 horas desde que se creó la fila. El doble de la ventana de una
hora que `api.codigos_acceso.canjear()` usa para sumar `intentos` y sostener
el techo de intentos de RF9 (Hallazgo 1, mismo repaso) — margen de sobra
para no interferir con esa cuenta mientras todavía puede importar. Sólo se
borran filas ya VENCIDAS o ya USADAS: una fila vigente nunca se toca, sin
importar su edad (hoy `CODIGO_TTL_MINUTOS` es 10, así que ninguna vigente
llega a las 2 horas, pero el filtro queda explícito por si ese valor cambia).

Corre como Scheduled Task de Coolify, igual que `reanudar_informes` e
`informe_diario` (ver CLAUDE.md): no hay nada en el repo que la programe.
"""
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from api.models import CodigoAcceso

RETENCION_HORAS = 2


class Command(BaseCommand):
    help = "Borra códigos de acceso vencidos o usados con más de 2 horas de antigüedad."

    def handle(self, *args, **opts):
        ahora = timezone.now()
        limite = ahora - timezone.timedelta(hours=RETENCION_HORAS)
        borrados, _ = CodigoAcceso.objects.filter(
            Q(usado_en__isnull=False) | Q(expira_en__lt=ahora),
            creado_en__lt=limite,
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"{borrados} códigos de acceso borrados"))
