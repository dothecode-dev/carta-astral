"""Termina los informes que quedaron a medias.

`INTENTOS_MAXIMOS` estaba escrito desde la Task 10 pero nadie gastaba el
segundo intento ni el tercero: el hilo de `InterpretationView.post` hace UNO y
muere. Si una sección falla, `completar_generacion` loguea, deja `intentos=1`,
suelta el lock y termina; nada lo vuelve a llamar. Un informe pago se quedaba
a medias para siempre y la carta volvía a ofrecer comprarlo (ver el cambio de
`en_curso` en `api/views.py`).

Este comando es el "alguien" que faltaba. Lo dispara la tarea programada de
Coolify cada pocos minutos, y se puede correr a mano para rescatar lo ya
caído. No duplica ninguna lógica: elige a quién le toca y llama a la misma
`completar_generacion` que usa el request, que ya sabe tomar el lock, reanudar
desde las secciones escritas, contar el intento y —agotados los tres— devolver
el derecho y avisar.
"""

import logging

from django.core.management.base import BaseCommand

from api import interpretation_service as svc
from api.models import Interpretation
from interpret.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reanuda los informes incompletos que nadie está escribiendo."

    def handle(self, *args, **options):
        # `account__isnull=False`: el FK es SET_NULL, así que una cuenta
        # borrada deja la fila sin dueño. No hay a quién entregarle el informe
        # ni a quién devolverle el derecho si falla, y `completar_generacion`
        # necesita la cuenta para liquidar.
        candidatas = Interpretation.objects.filter(
            completa=False,
            prompt_version=PROMPT_VERSION,
            intentos__lt=svc.INTENTOS_MAXIMOS,
            account__isnull=False,
        ).select_related("chart", "account")

        reanudados = 0
        fallidos = 0
        for interpretacion in candidatas:
            # El lock vivo significa que hay un hilo escribiendo ESTA misma
            # interpretación ahora mismo. `completar_generacion` lo chequea
            # igual y se retira solo, pero saltearlo acá evita el trabajo y
            # deja el contador diciendo la verdad.
            if svc.esta_generandose(interpretacion.chart, interpretacion.tier):
                continue
            try:
                svc.completar_generacion(
                    interpretacion, interpretacion.chart, interpretacion.account
                )
            except Exception:
                # Esto procesa una cola, no un caso: un informe que revienta
                # por algo que `completar_generacion` no contempla no puede
                # frenar a todos los que vengan detrás en la misma corrida.
                fallidos += 1
                logger.exception(
                    "no se pudo reanudar el informe %s", interpretacion.pk
                )
            else:
                reanudados += 1

        self.stdout.write(f"informes reanudados: {reanudados} (fallidos: {fallidos})")
