"""El tope diario de generaciones gratis, por ámbito, sin carreras.

`reservar` toma un lugar antes de generar; `devolver` lo suelta si la
generación falló. La fila del día se crea al primer uso.
"""
import datetime as dt
import logging

from django.db.models import F
from django.utils import timezone

from api.models import CupoDiario

logger = logging.getLogger(__name__)

ANONIMO = "anonimo"
CUENTA = "cuenta"


def reservar(ambito: str, tope: int) -> dt.date | None:
    """La fecha (UTC) de la reserva, o `None` si el cupo del día está lleno."""
    hoy = timezone.now().date()
    CupoDiario.objects.get_or_create(fecha=hoy, ambito=ambito)
    tomadas = CupoDiario.objects.filter(
        fecha=hoy, ambito=ambito, usados__lt=tope,
    ).update(usados=F("usados") + 1)
    return hoy if tomadas == 1 else None


def devolver(ambito: str, fecha: dt.date) -> None:
    """Suelta un lugar de `fecha`. Nunca deja el contador debajo de cero."""
    CupoDiario.objects.filter(
        fecha=fecha, ambito=ambito, usados__gt=0,
    ).update(usados=F("usados") - 1)
