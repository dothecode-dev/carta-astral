"""Hallazgo 5 de la re-revisión de `puertas-de-acceso`: sin la
`UniqueConstraint` que el `pedir()` viejo usaba (Hallazgo I1), las filas de
`CodigoAcceso` ya no se pisan ni se marcan `usado_en` al vencer — se
acumulan indefinidamente, hasta 5 por dirección, incluso las de gente que
nunca llegó a tener cuenta. Es retención de PII sin plazo, no prolijidad.

El comando borra sólo lo que ya no hace falta: filas vencidas o usadas, y
con más de `RETENCION_HORAS` desde que se crearon. Ese margen no es
arbitrario: `codigos_acceso.canjear()` (Hallazgo 1, mismo repaso) suma
`intentos` sobre una ventana de la última hora para sostener el techo de
intentos — si el comando borrara una fila recién vencida, le sacaría su
aporte a esa suma antes de que la ventana la descarte sola. El doble de
margen (2 horas) es barato y deja tranquilo ese cálculo.
"""
import io

import pytest
from django.core.management import call_command
from django.utils import timezone

from api.models import CodigoAcceso

pytestmark = pytest.mark.django_db


def _crear(email, *, creado_hace, vigente=True, usada=False):
    ahora = timezone.now()
    fila = CodigoAcceso.objects.create(
        email=email,
        codigo_hash="a" * 64,
        expira_en=ahora + timezone.timedelta(minutes=10) if vigente
        else ahora - timezone.timedelta(minutes=1),
    )
    # `creado_en` es `auto_now_add`: se pisa después con un `update()` crudo,
    # que no dispara `auto_now_add` de nuevo.
    CodigoAcceso.objects.filter(pk=fila.pk).update(
        creado_en=ahora - creado_hace,
        usado_en=ahora - creado_hace if usada else None,
    )
    return CodigoAcceso.objects.get(pk=fila.pk)


def test_borra_una_fila_vencida_y_vieja():
    vieja = _crear("juan@gmail.com", creado_hace=timezone.timedelta(hours=3), vigente=False)
    call_command("purgar_codigos_acceso")
    assert not CodigoAcceso.objects.filter(pk=vieja.pk).exists()


def test_borra_una_fila_usada_y_vieja():
    vieja = _crear("juan@gmail.com", creado_hace=timezone.timedelta(hours=3), usada=True)
    call_command("purgar_codigos_acceso")
    assert not CodigoAcceso.objects.filter(pk=vieja.pk).exists()


def test_no_borra_una_fila_vigente_aunque_sea_vieja():
    """No debería poder pasar con `CODIGO_TTL_MINUTOS` en 10, pero el filtro
    queda explícito: nunca se borra una fila vigente, sin importar la edad."""
    vigente = _crear("juan@gmail.com", creado_hace=timezone.timedelta(hours=3), vigente=True)
    call_command("purgar_codigos_acceso")
    assert CodigoAcceso.objects.filter(pk=vigente.pk).exists()


def test_no_borra_una_fila_vencida_reciente():
    """Dentro de la ventana de intentos (la última hora): borrarla le
    restaría su aporte a la suma que sostiene el techo de RF9."""
    reciente = _crear("juan@gmail.com", creado_hace=timezone.timedelta(minutes=30), vigente=False)
    call_command("purgar_codigos_acceso")
    assert CodigoAcceso.objects.filter(pk=reciente.pk).exists()


def test_no_borra_una_fila_usada_reciente():
    reciente = _crear("juan@gmail.com", creado_hace=timezone.timedelta(minutes=30), usada=True)
    call_command("purgar_codigos_acceso")
    assert CodigoAcceso.objects.filter(pk=reciente.pk).exists()


def test_reporta_cuantas_filas_borro():
    _crear("juan@gmail.com", creado_hace=timezone.timedelta(hours=3), vigente=False)
    _crear("ceci@gmail.com", creado_hace=timezone.timedelta(hours=3), usada=True)
    out = io.StringIO()
    call_command("purgar_codigos_acceso", stdout=out)
    assert "2" in out.getvalue()
