import datetime

import pytest
from django.core.cache import cache
from django.conf import settings as django_settings

from api import informe_service
from api import interpretation_service as svc
from api.models import Account, BirthData, Chart, Interpretation
from interpret.exceptions import InterpretationError

pytestmark = pytest.mark.django_db


def _account(free_balance=None, paid_balance=0):
    fb = django_settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
    return Account.objects.create(free_balance=fb, paid_balance=paid_balance)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _chart():
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data={"time_known": True}, engine_version="test")


def _chart_with_data(data):
    bd = BirthData.objects.create(
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
        tz_name="America/Argentina/Buenos_Aires",
    )
    return Chart.objects.create(birth_data=bd, data=data, engine_version="test")


def _generar(chart, lang, account, tier="largo"):
    """Arranca y completa un informe sincrónicamente, como hace
    `generar_en_segundo_plano`, devolviendo la `Interpretation` ya
    completada. El refresh es necesario: cuando `completar_generacion` toma
    el camino de traducir un sibling (`informe_service.traducir_informe`),
    el texto se escribe sobre OTRA instancia obtenida con `get_or_create`
    adentro de esa función, no sobre el objeto `interp` que tenemos acá.
    tier="largo" por default: este archivo prueba el flujo del informe
    completo."""
    interp = svc.iniciar_generacion(chart, lang, account, tier=tier)
    svc.completar_generacion(interp, chart, account)
    interp.refresh_from_db()
    return interp


class _Stream:
    def __init__(self, resp=None, raises=None):
        self._resp = resp
        self._raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._raises:
            raise self._raises

        class R:
            content = [type("B", (), {"type": "text", "text": "una interpretación"})()]
            stop_reason = "end_turn"

        return R()


class _FakeClient:
    calls = 0

    class _M:
        def stream(self, **kw):
            _FakeClient.calls += 1
            return _Stream()

    @property
    def messages(self):
        return _FakeClient._M()


class _Boom:
    class _M:
        def stream(self, **kw):
            import anthropic

            return _Stream(raises=anthropic.AnthropicError("boom"))

    @property
    def messages(self):
        return _Boom._M()


@pytest.fixture
def fake_client(monkeypatch):
    _FakeClient.calls = 0
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())
    return _FakeClient


# Ocho secciones aplican siempre en estos tests: `_chart()`/`_chart_with_data`
# ponen `time_known=True`, así que ninguna sección con `requiere_hora` se
# excluye (`informe_service.secciones_aplicables`). Cada sección es una
# llamada al LLM (`build_seccion`), así que una generación completa cuenta
# ocho contra `fake_client.calls`, no una como en el flujo viejo (que armaba
# el texto entero en un único llamado).
SECCIONES_POR_INFORME = 8


def test_miss_generates_and_persists(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    # paid_balance=1: `_generar` pide tier="largo" (informe completo) por
    # default, que desde la Task 6 cobra del lote paid, no del free.
    interp = _generar(c, "es", _account(paid_balance=1))
    assert interp.completa is True
    assert "una interpretación" in interp.text
    assert Interpretation.objects.count() == 1
    assert fake_client.calls == SECCIONES_POR_INFORME


def test_hit_serves_without_llm(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    acc = _account(paid_balance=1)
    _generar(c, "es", acc)
    llamadas_tras_la_primera = fake_client.calls
    _generar(c, "es", acc)
    assert fake_client.calls == llamadas_tras_la_primera
    assert Interpretation.objects.count() == 1


def test_daily_cap_blocks_new_generation(fake_client, settings):
    """El cap sólo protege el lote free (Task 6, RF9): con dos tiers, "ambas
    generaciones son gratis" ya no es una elección de saldo (como antes de
    esta tarea) sino del producto pedido — `tier="corto"` es la única forma
    de tocar el lote free, así que el cap se ejercita ahí, no con
    `tier="largo"` (que siempre cobra paid y siempre bypassea el cap, ver
    `test_paid_generation_bypasses_daily_cap` en `test_credits_quota.py`)."""
    from django.utils import timezone

    settings.INTERPRETATION_DAILY_CAP = 1
    settings.INSTALL_FREE_CREDITS = 5  # both generations are free, to isolate the cap
    acc = _account()  # free_balance=5 (reads settings at call time)
    _generar(_chart(), "es", acc, tier="corto")
    # El contador se mueve exactamente una vez por generación free, no una
    # vez por sección (minor 5, fix round 1): la breve hace una sola llamada
    # al LLM, así que esto no distingue "una vez" de "una por llamada" tan
    # claramente como el informe completo, pero sigue siendo la única forma
    # de ejercitar el contador ahora que sólo el lote free lo toca.
    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    assert cache.get(cap_key) == 1
    llamadas_tras_la_primera = fake_client.calls
    with pytest.raises(svc.CapReached):
        # el cap se chequea (y cuenta) en `iniciar_generacion`, antes de
        # arrancar ninguna sección: una carta con datos distintos no dedupea
        # (no hay dedup contra el camino nuevo, ver concern en el reporte de
        # la Task 0) y de todas formas choca contra el cap ya consumido.
        svc.iniciar_generacion(
            _chart_with_data({"time_known": True, "utc_iso": "1990-01-01T00:00:00Z"}), "es", acc,
            tier="corto",
        )
    assert fake_client.calls == llamadas_tras_la_primera  # sólo la primera generación llegó a pedirle al LLM


def test_cap_does_not_block_cache_hits(fake_client, settings):
    settings.INTERPRETATION_DAILY_CAP = 1
    c = _chart()
    acc = _account(paid_balance=1)
    first = _generar(c, "es", acc)
    again = _generar(c, "es", acc)
    assert again.text == first.text
    assert fake_client.calls == SECCIONES_POR_INFORME


def test_llm_error_no_deja_interpretacion_persistida(monkeypatch, settings):
    """Contrapunto del flujo viejo: ahí el error del LLM se propagaba
    sincrónicamente como `InterpretationError` hasta quien llamaba a
    `get_or_create_interpretation`. Desde la Tarea 10 la generación real
    corre en `completar_generacion`, que atrapa y loguea cualquier excepción
    en vez de relanzarla (es la función que corre en el hilo de fondo; ver
    su docstring). Lo que sigue valiendo acá no es "se levanta la
    excepción" sino la garantía de plata: si el LLM falla SIEMPRE, agotados
    `INTENTOS_MAXIMOS` reintentos (Task 10 / RF21) no queda ninguna
    `Interpretation` a medias ni se pierde el crédito cobrado."""
    settings.INTERPRETATION_DAILY_CAP = 100
    monkeypatch.setattr(svc, "_build_client", lambda: _Boom())
    c = _chart()
    acc = _account(paid_balance=1)  # tier="largo" (informe completo) cobra paid, no free
    antes = acc.free_balance + acc.paid_balance
    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.generar_en_segundo_plano(c, "es", acc, tier="largo")
    assert Interpretation.objects.count() == 0
    acc.refresh_from_db()
    assert acc.free_balance + acc.paid_balance == antes


def test_missing_api_key_no_deja_interpretacion_persistida(settings):
    """Mismo comportamiento que el error del LLM (arriba) para el otro
    disparador que ya cubría el flujo viejo: sin `ANTHROPIC_API_KEY`,
    `_build_client` levanta `InterpretationError` dentro de
    `completar_generacion`, que la atrapa sin dejar nada a medias — recién
    al agotar `INTENTOS_MAXIMOS` reintentos (Task 10 / RF21)."""
    settings.INTERPRETATION_DAILY_CAP = 100
    settings.ANTHROPIC_API_KEY = ""
    c = _chart()
    acc = _account(paid_balance=1)  # tier="largo" (informe completo) cobra paid, no free
    antes = acc.free_balance + acc.paid_balance
    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.generar_en_segundo_plano(c, "es", acc, tier="largo")
    assert Interpretation.objects.count() == 0
    acc.refresh_from_db()
    assert acc.free_balance + acc.paid_balance == antes


def test_missing_api_key_sigue_levantando_interpretation_error_desde_build_client():
    """`_build_client` en sí (no el flujo completo) sigue levantando un
    error prolijo y no un `TypeError` crudo del SDK: eso es lo que
    `completar_generacion` necesita poder atrapar como excepción conocida."""
    from django.test import override_settings

    with override_settings(ANTHROPIC_API_KEY=""):
        with pytest.raises(InterpretationError):
            svc._build_client()


# --- una interpretación por carta; otros idiomas = traducción gratis ---


@pytest.fixture
def fake_translator(monkeypatch):
    """El camino nuevo traduce sección por sección
    (`informe_service.traducir_informe`), que importa `translate_interpretation`
    directo de `interpret.generator` — no a través de `interpretation_service`.
    Por eso el mock va sobre `informe_service`, no sobre `svc` (a diferencia
    del flujo viejo, que traducía el texto entero en una sola llamada propia)."""
    calls = []
    monkeypatch.setattr(
        informe_service, "translate_interpretation",
        lambda text, lang, client: calls.append((text, lang)) or f"[{lang}] {text}",
    )
    return calls


def test_second_lang_translates_without_new_generation_nor_charge(fake_client, fake_translator, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    # free_balance=0, paid_balance=1: informe completo (tier="largo", el
    # default de `_generar`) cobra paid desde la Task 6.
    acc = _account(free_balance=0, paid_balance=1)
    _generar(c, "es", acc)  # cobra el único crédito
    llamadas_generacion = fake_client.calls
    second = _generar(c, "en", acc)
    assert fake_client.calls == llamadas_generacion  # ninguna generación real nueva
    # Una traducción por sección (ocho), no una por informe entero como en
    # el flujo viejo: `traducir_informe` traduce de a un texto por llamada.
    assert len(fake_translator) == SECCIONES_POR_INFORME
    assert all(texto == "una interpretación" and lang == "en" for texto, lang in fake_translator)
    assert second.lang == "en"
    assert "[en] una interpretación" in second.text
    acc.refresh_from_db()
    assert svc.credits_available(acc) == 0  # no cobró el segundo idioma


def test_translation_available_with_zero_credits(fake_client, fake_translator, settings):
    settings.INTERPRETATION_DAILY_CAP = 100
    c = _chart()
    acc = _account(free_balance=0, paid_balance=1)
    _generar(c, "es", acc)  # gasta el último crédito
    # ya sin saldo, el cambio de idioma sigue funcionando (la carta ya se pagó)
    out = _generar(c, "pt", acc)
    assert "[pt] una interpretación" in out.text


def test_translation_does_not_consume_daily_cap(fake_client, fake_translator, settings):
    """tier="corto" en los tres llamados (Task 6): el cap sólo se mueve con
    el lote free, y desde RF9 el único tier que lo toca es la lectura breve
    — con tier="largo" (paid) el cap nunca se alcanzaría y este test no
    probaría nada (ver `test_daily_cap_blocks_new_generation`, arriba)."""
    settings.INTERPRETATION_DAILY_CAP = 1
    settings.INSTALL_FREE_CREDITS = 5
    c = _chart()
    _generar(c, "es", _account(), tier="corto")
    _generar(c, "en", _account(free_balance=1), tier="corto")
    with pytest.raises(svc.CapReached):
        svc.iniciar_generacion(
            _chart_with_data({"time_known": True, "utc_iso": "1990-01-01T00:00:00Z"}), "es", _account(),
            tier="corto",
        )


# --- CONCERN (Task 0): dedup por content_key entre cartas idénticas ---
#
# El flujo viejo (`get_or_create_interpretation`, borrado acá) buscaba un
# "donante" por `content_key` antes de llamarle al LLM: dos cartas con el
# mismo input astrológico compartían el texto sin pagar una segunda
# generación. Esa lógica de reutilización NUNCA se migró a
# `iniciar_generacion`/`completar_generacion`/`informe_service.generar_informe`
# — ninguno de los tres calcula ni consulta `content_key` hoy; las filas que
# crea `iniciar_generacion` ni siquiera lo completan (queda en su default
# `""`). El pre-flight scan de la Task 2 (`content_key(chart_data, lang,
# prompt_version, tier)`) asume que ya existe un llamador de `content_key`
# "donde lo use el flujo de informe" — hoy no lo hay.
#
# No se migró una versión "equivalente" de este comportamiento contra el
# camino nuevo porque implementarla es una decisión de diseño fuera del
# alcance de esta tarea (¿el donante se busca por el `content_key` del
# informe entero, como antes, o por sección, ahora que la generación es
# seccionada?) — no un renombre mecánico de una llamada existente. Se
# reporta como concern en vez de inventar el mecanismo acá. Mientras tanto
# sólo se prueba la función hash en sí (que Task 2 va a extender con
# `tier`), no su integración: eso es lo que se perdió respecto de la
# cobertura del flujo viejo.


def test_content_key_es_estable_para_el_mismo_input():
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z", "placements": [1, 2]}
    assert svc.content_key(data, "es", "v1", "largo") == svc.content_key(dict(data), "es", "v1", "largo")


def test_content_key_cambia_con_datos_lang_o_prompt_version_distintos():
    data = {"time_known": True, "utc_iso": "1989-07-15T02:45:00Z"}
    base = svc.content_key(data, "es", "v1", "largo")
    assert svc.content_key({**data, "utc_iso": "1989-07-15T02:46:00Z"}, "es", "v1", "largo") != base
    assert svc.content_key(data, "en", "v1", "largo") != base
    assert svc.content_key(data, "es", "v2", "largo") != base
