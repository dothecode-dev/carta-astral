import pytest
from django.core.cache import cache

from api import interpretation_service
from api.exceptions import GenerationInProgress
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db


def test_una_generacion_en_curso_bloquea_tambien_los_otros_idiomas(db_cache, chart, account):
    # Pedir el informe en español y cambiar a inglés a mitad disparaba dos
    # generaciones de cuatro minutos y cobraba dos créditos por la misma carta.
    cache.set(f"interp:lock:{chart.id}:{PROMPT_VERSION}", "1", timeout=600)
    with pytest.raises(GenerationInProgress):
        interpretation_service.get_or_create_interpretation(chart, "en", account)


def test_el_ttl_cubre_lo_que_tarda_un_informe_de_ocho_secciones():
    # Ocho llamadas de ~30 s no entran en 30 segundos.
    assert interpretation_service.LOCK_TTL >= 8 * 60


def test_renovar_lock_repone_el_ttl_de_un_lock_existente(db_cache, chart):
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    token = "tok-propio"
    cache.set(key, token, timeout=1)
    assert interpretation_service.renovar_lock(chart, token) is True
    import time

    # Si no se repuso el TTL, esto ya habría expirado.
    time.sleep(1.2)
    assert cache.get(key) == token


def test_renovar_lock_no_crea_el_lock_si_no_existe(db_cache, chart):
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    assert cache.get(key) is None
    assert interpretation_service.renovar_lock(chart, "token-cualquiera") is False
    assert cache.get(key) is None


def test_renovar_lock_no_extiende_un_lock_vencido_con_fila_sin_purgar(db_cache, chart):
    """Reproduce lo que encontró la revisión contra `DatabaseCache`: `touch()`
    no compara expiración (ese chequeo sólo existe para `add`, en
    `_base_set`), así que una fila vencida que el purgado todavía no borró
    podía resucitar 600 s más. `renovar_lock` no puede confiar sólo en
    `touch()`: tiene que chequear con `get()` primero, que sobre
    `DatabaseCache` purga la fila vencida al leerla.

    Este test sólo puede fallar de la forma correcta contra `DatabaseCache`:
    `LocMemCache` chequea `_has_expired` antes de tocar la clave, así que ahí
    el bug no se puede ver — por eso corre con `db_cache`.
    """
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    token = "tok-vencido"
    # timeout negativo: la fila queda escrita con expires en el pasado sin
    # pasar por get()/cull, que es lo que la purgaría. Simula la fila vencida
    # "todavía no purgada" que reprodujo la revisión.
    cache.set(key, token, timeout=-1)
    assert interpretation_service.renovar_lock(chart, token) is False
    # No debe haber quedado resucitada ni extendida.
    assert cache.get(key) is None


def test_renovar_lock_no_pisa_el_lock_de_otro_proceso(db_cache, chart):
    """Proceso A toma el lock, expira, proceso B lo toma. A todavía guarda su
    token viejo: renovar con ese token no puede pisar el lock de B."""
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    token_a = "tok-a"
    token_b = "tok-b"
    cache.set(key, token_a, timeout=-1)  # el lock de A ya venció
    assert cache.add(key, token_b, timeout=interpretation_service.LOCK_TTL)  # B lo toma
    assert interpretation_service.renovar_lock(chart, token_a) is False
    assert cache.get(key) == token_b
