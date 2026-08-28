import pytest
from django.core.cache import cache

from api import interpretation_service
from api.exceptions import GenerationInProgress
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def test_una_generacion_en_curso_bloquea_tambien_los_otros_idiomas(chart, account):
    # Pedir el informe en español y cambiar a inglés a mitad disparaba dos
    # generaciones de cuatro minutos y cobraba dos créditos por la misma carta.
    cache.set(f"interp:lock:{chart.id}:{PROMPT_VERSION}", "1", timeout=600)
    with pytest.raises(GenerationInProgress):
        interpretation_service.get_or_create_interpretation(chart, "en", account)


def test_el_ttl_cubre_lo_que_tarda_un_informe_de_ocho_secciones():
    # Ocho llamadas de ~30 s no entran en 30 segundos.
    assert interpretation_service.LOCK_TTL >= 8 * 60


def test_renovar_lock_repone_el_ttl_de_un_lock_existente(chart):
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    cache.set(key, "1", timeout=1)
    assert interpretation_service.renovar_lock(chart) is True
    # Si no se repuso el TTL, esto ya habría expirado.
    import time

    time.sleep(1.2)
    assert cache.get(key) == "1"


def test_renovar_lock_no_crea_el_lock_si_no_existe(chart):
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    assert cache.get(key) is None
    assert interpretation_service.renovar_lock(chart) is False
    assert cache.get(key) is None
