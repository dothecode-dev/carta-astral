"""`manage.py check` tiene que salir limpio, y los silencios tienen que caducar.

Una salida con warnings permanentes que nadie puede accionar entrena a ignorar
el comando entero: cuando aparezca uno que sí importa, va a pasar de largo. Por
eso el único warning que hoy queda —`treebeard.E001`, de Wagtail— está
silenciado en settings, y por eso el segundo test de este archivo existe: el
día que Wagtail arregle su manager, el silencio sobra y hay que sacarlo.
"""
import pytest
from django.core.checks import run_checks


def test_no_quedan_avisos_sin_accionar():
    sin_silenciar = [aviso for aviso in run_checks() if not aviso.is_silenced()]

    assert sin_silenciar == []


def test_el_silencio_de_treebeard_sigue_haciendo_falta():
    """Si esto falla, Wagtail ya lo arregló: sacar SILENCED_SYSTEM_CHECKS.

    `Page.objects` es un `BasePageManager`, que hoy hereda de `models.Manager`
    y no de `MP_NodeManager` (wagtail/models/pages.py). Mientras siga así, el
    warning aparece para `Page`, `Collection` y cada modelo del CMS que herede
    de `Page`, y no hay nada que podamos hacer desde este repo.
    """
    from treebeard.mp_tree import MP_NodeManager
    from wagtail.models import Page

    assert not issubclass(type(Page.objects), MP_NodeManager)


@pytest.mark.django_db
def test_el_check_de_migraciones_no_encuentra_cambios_pendientes():
    """Un modelo tocado sin su migración rompe el deploy, no el test suite."""
    from io import StringIO

    from django.core.management import call_command

    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())
