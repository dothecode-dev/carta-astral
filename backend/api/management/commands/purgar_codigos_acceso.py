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

También borra las filas vencidas de la caché de la base: `DatabaseCache` sólo
las elimina al releerlas o al podar, así que sin esto se acumulan (y con ellas
datos que la política de privacidad promete no retener).

Corre como Scheduled Task de Coolify, igual que `reanudar_informes` e
`informe_diario` (ver CLAUDE.md): no hay nada en el repo que la programe.
"""
import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from api.models import CodigoAcceso, EntradaCache

logger = logging.getLogger(__name__)

RETENCION_HORAS = 2
_DB_CACHE = "django.core.cache.backends.db.DatabaseCache"


def _purgar_cache_vencida(ahora) -> int:
    """Borra las filas vencidas de la caché de la base. `DatabaseCache` sólo
    las borra al releerlas o al podar; esto es lo que hace cierta la promesa
    de retención de la política de privacidad."""
    conf = settings.CACHES.get("default", {})
    if conf.get("BACKEND") != _DB_CACHE:
        return 0
    tabla = EntradaCache._meta.db_table
    if conf.get("LOCATION") != tabla:
        # `config/caches.py` fija la LOCATION y un test la ata al modelo:
        # llegar acá es que alguien las separó. Mejor no borrar nada que
        # borrar en la tabla equivocada.
        logger.error(
            "purga de caché salteada: LOCATION=%r no es la tabla del modelo (%r)",
            conf.get("LOCATION"), tabla,
        )
        return 0
    borradas, _ = EntradaCache.objects.filter(expires__lt=ahora).delete()
    return borradas


class Command(BaseCommand):
    help = (
        "Borra códigos de acceso vencidos o usados con más de 2 horas de antigüedad "
        "y las entradas vencidas de la caché de la base."
    )

    def handle(self, *args, **opts):
        ahora = timezone.now()
        limite = ahora - timezone.timedelta(hours=RETENCION_HORAS)
        borrados, _ = CodigoAcceso.objects.filter(
            Q(usado_en__isnull=False) | Q(expira_en__lt=ahora),
            creado_en__lt=limite,
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"{borrados} códigos de acceso borrados"))
        vencidas = _purgar_cache_vencida(ahora)
        self.stdout.write(self.style.SUCCESS(f"{vencidas} entradas vencidas de la caché borradas"))
