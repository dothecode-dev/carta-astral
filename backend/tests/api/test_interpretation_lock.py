import pytest
from django.core.cache import cache

from api import interpretation_service
from api.exceptions import GenerationInProgress
from api.models import Interpretation
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db


def test_interpretacion_en_curso_con_lock_vivo_bloquea_otro_idioma(db_cache, chart, account):
    """Contrapunto de `test_interpretacion_abandonada_sin_lock_no_bloquea_otro_idioma`
    (más abajo): con el lock realmente tomado —generación en curso de
    verdad, no una abandonada— pedir el otro idioma sí se rechaza.

    Reemplaza, contra el camino nuevo, a
    `test_una_generacion_en_curso_bloquea_tambien_los_otros_idiomas`
    (retirado junto con `get_or_create_interpretation` en la Task 0): aquel
    test tomaba el lock sin que existiera ninguna `Interpretation` en curso,
    una escena que ya no puede darse — en este módulo el lock de la carta
    sólo lo toma `completar_generacion`, siempre sobre una fila que
    `iniciar_generacion` ya creó antes. El caso realista (fila + lock) ya
    está cubierto con más detalle, incluido el saldo, por
    `test_informe_endpoint.py::test_pedir_el_segundo_idioma_con_el_primero_en_curso_no_cobra`."""
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    cache.set(f"interp:lock:{chart.id}:{PROMPT_VERSION}", "token-vivo", timeout=600)
    with pytest.raises(GenerationInProgress):
        interpretation_service.iniciar_generacion(chart, "en", account)


# --- HALLAZGO 2 de code review: `_sibling_en_curso` sin límite de antigüedad ---
# Cualquier `Interpretation` que quede `completa=False` bloqueaba con 409 el
# resto de los idiomas de esa carta para siempre: un restart de gunicorn a
# mitad de generación, o el techo de tokens del HALLAZGO 1, sueltan el lock
# de la carta (por TTL o al terminar `completar_generacion`) pero dejan la
# fila `completa=False` — y `_sibling_en_curso` sólo miraba esa fila, nunca
# el lock. Criterio elegido: lock VIVO (`cache.get(_lock_key(chart))`), el
# mismo mecanismo que ya usan `renovar_lock`/`soltar_lock` en este módulo —
# sin lock, no hay ningún proceso generando esta carta ahora mismo, así que
# un `completa=False` sin lock es un abandonado, no "en curso".


def test_sibling_en_curso_ignora_una_interpretacion_abandonada_sin_lock(db_cache, chart, account):
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    # No se toma ningún lock: simula un proceso muerto (restart de gunicorn a
    # mitad de generación, o el fallo terminal del HALLAZGO 1) que ya no
    # sostiene el candado de la carta.
    assert interpretation_service._sibling_en_curso(chart, "en") is None


def test_sibling_en_curso_sigue_bloqueando_con_el_lock_vivo(db_cache, chart, account):
    """Contrapunto: con el lock realmente tomado, el criterio nuevo sigue
    detectando la generación en curso igual que antes."""
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    cache.set(f"interp:lock:{chart.id}:{PROMPT_VERSION}", "token-vivo", timeout=600)
    sibling = interpretation_service._sibling_en_curso(chart, "en")
    assert sibling is not None
    assert sibling.lang == "es"


def test_interpretacion_abandonada_sin_lock_no_bloquea_otro_idioma(db_cache, chart, account):
    """Nivel de comportamiento (no sólo la función privada): pedir el otro
    idioma sobre una carta con un informe abandonado no puede quedar
    bloqueado para siempre — `iniciar_generacion` tiene que poder seguir."""
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )
    otra = interpretation_service.iniciar_generacion(chart, "en", account)
    assert otra.lang == "en"


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


def test_soltar_lock_libera_el_propio(db_cache, chart):
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    token = "tok-propio"
    cache.set(key, token, timeout=interpretation_service.LOCK_TTL)
    interpretation_service.soltar_lock(chart, token)
    assert cache.get(key) is None


def test_soltar_lock_no_toca_el_ajeno(db_cache, chart):
    """Proceso A toma el lock, expira, proceso B lo toma. A llama a
    soltar_lock con su token viejo y el lock de B queda intacto."""
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    token_a = "tok-a"
    token_b = "tok-b"
    cache.set(key, token_a, timeout=-1)  # el lock de A ya venció
    assert cache.add(key, token_b, timeout=interpretation_service.LOCK_TTL)  # B lo toma
    interpretation_service.soltar_lock(chart, token_a)
    assert cache.get(key) == token_b
