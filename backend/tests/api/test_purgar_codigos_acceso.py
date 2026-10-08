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
import datetime as dt
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


def _fila_cache(clave, expira):
    from api.models import EntradaCache

    EntradaCache.objects.create(cache_key=clave, value="x", expires=expira)


def _claves_cache():
    from api.models import EntradaCache

    return set(EntradaCache.objects.values_list("cache_key", flat=True))


def test_el_modelo_apunta_a_la_tabla_de_la_cache_de_produccion():
    """El modelo no gestionado fija la tabla; `config/caches.py` fija la
    LOCATION. Si se separan, la purga borraría en otra tabla (o en ninguna)."""
    from api.models import EntradaCache
    from config import caches

    assert EntradaCache._meta.managed is False
    assert EntradaCache._meta.db_table == caches.armar(usar_db=True, debug=False)["default"]["LOCATION"]


def test_una_location_distinta_no_borra_nada(db_cache, settings, caplog):
    ahora = timezone.now()
    _fila_cache(":1:vieja", ahora - dt.timedelta(minutes=1))
    real = settings.CACHES
    settings.CACHES = {"default": {**real["default"], "LOCATION": "otra_tabla"}}
    try:
        with caplog.at_level("ERROR"):
            call_command("purgar_codigos_acceso")
    finally:
        settings.CACHES = real  # el teardown de `db_cache` limpia la tabla real
    assert _claves_cache() == {":1:vieja"}
    assert any("otra_tabla" in r.getMessage() for r in caplog.records)


def test_borra_las_filas_vencidas_de_la_cache(db_cache):
    ahora = timezone.now()
    _fila_cache(":1:vieja", ahora - dt.timedelta(minutes=1))
    _fila_cache(":1:viva", ahora + dt.timedelta(hours=1))
    call_command("purgar_codigos_acceso")
    assert _claves_cache() == {":1:viva"}


def test_sin_cache_de_base_no_hace_nada(settings):
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    call_command("purgar_codigos_acceso")  # no revienta
