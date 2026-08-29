"""Backfill de `completa` (migración `0020_backfill_completa`) para
interpretaciones que ya existían antes de la Tarea 10: texto completo, sin
ninguna `InterpretationSection` (ese modelo no existía todavía), y
`completa=False` porque `0019` agrega el campo con ese default y sin
backfill propio.

Encontrado en re-revisión de la Tarea 10, no hipotético: sin este backfill,
el 100% de lo que ya existe en producción se reporta como "no disponible"
—el bug exacto que la Tarea 10 debía cerrar— y un reintento del usuario
hace que `completar_generacion` regenere las ocho secciones desde cero
sobre un texto que ya estaba; si esa regeneración falla antes de persistir
una sección, borra la interpretación original y acredita un crédito que
nunca se cobró en ese intento.
"""

import importlib

import pytest
from django.apps import apps as django_apps

from api.models import Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

_backfill = importlib.import_module("api.migrations.0020_backfill_completa").backfill


def _correr_backfill():
    _backfill(django_apps, None)


def _interpretacion_legacy(chart, account):
    """Como quedaría en producción una interpretación del flujo viejo:
    texto completo, cero secciones persistidas, `completa=False` por el
    default que puso `0019` al agregar el campo."""
    return Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION,
        text="Un informe ya escrito antes de la Tarea 10.",
        account=account, content_key="legacy", completa=False,
    )


def test_marca_completa_la_fila_legacy(chart, account):
    legacy = _interpretacion_legacy(chart, account)
    _correr_backfill()
    legacy.refresh_from_db()
    assert legacy.completa is True


def test_no_toca_una_generacion_real_en_curso(chart, account):
    """Contrapunto: una fila de la Tarea 10 a medio generar tiene
    `completa=False` Y `text=""` siempre (`generar_informe` sólo escribe
    `text` en el mismo `save()` atómico que pone `completa=True`) — nunca
    matchea el marcador legacy, así que el backfill no debe tocarla."""
    from api import interpretation_service as svc

    en_curso = svc.iniciar_generacion(chart, "es", account, tier="largo")
    assert en_curso.completa is False
    assert en_curso.text == ""

    _correr_backfill()

    en_curso.refresh_from_db()
    assert en_curso.completa is False


def test_no_toca_una_generacion_con_secciones_pero_incompleta(chart, account):
    """Otra generación real: ya tiene una sección persistida pero no las
    ocho. Tampoco matchea (tiene al menos una sección)."""
    en_curso = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="",
        account=account, completa=False,
    )
    InterpretationSection.objects.create(interpretation=en_curso, slug="firma", orden=0, texto="x")

    _correr_backfill()

    en_curso.refresh_from_db()
    assert en_curso.completa is False


def test_es_idempotente(chart, account):
    legacy = _interpretacion_legacy(chart, account)
    _correr_backfill()
    _correr_backfill()  # segunda corrida: no debe fallar ni cambiar nada
    legacy.refresh_from_db()
    assert legacy.completa is True


def test_escenario_legacy_end_to_end(client_autenticado, chart, account, monkeypatch):
    """El caso que la re-revisión encontró sin cubrir: una interpretación
    legacy (completa=False, texto poblado, cero secciones) pasando por el
    GET, por `_chart_repr` y por `iniciar_generacion`/`completar_generacion`.
    Con el backfill aplicado tiene que verse como disponible en las tres
    superficies y NO disparar una regeneración."""
    from api import informe_service, interpretation_service as svc

    legacy = _interpretacion_legacy(chart, account)
    _correr_backfill()
    legacy.refresh_from_db()
    assert legacy.completa is True

    # 1) GET .../interpretation/: ya no es el 404 de "no disponible".
    resp = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/?lang=es")
    assert resp.status_code == 200
    assert resp.json()["text"] == legacy.text

    # 2) _chart_repr: la lista como idioma disponible.
    detail = client_autenticado.get(f"/api/charts/{chart.uuid}/")
    assert detail.json()["interpretation_langs"] == ["es"]

    # 3) iniciar_generacion: encuentra la fila existente y NO cobra de nuevo.
    antes = account.free_balance + account.paid_balance
    encontrada = svc.iniciar_generacion(chart, "es", account, tier="largo")
    assert encontrada.pk == legacy.pk
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes

    # 4) completar_generacion: el guard de `completa` corta antes de tomar
    # el lock o de tocar el LLM — no regenera nada.
    llamadas = []
    monkeypatch.setattr(informe_service, "generar_informe", lambda *a, **kw: llamadas.append(1))
    svc.completar_generacion(encontrada, chart, account)
    assert llamadas == []
    assert InterpretationSection.objects.filter(interpretation=encontrada).count() == 0
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes
    encontrada.refresh_from_db()
    assert encontrada.text == "Un informe ya escrito antes de la Tarea 10."
