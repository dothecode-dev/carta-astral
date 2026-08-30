"""Task 10 / RF21: o se entrega el informe completo, o se devuelve la plata.

La regla vieja devolvía el crédito sólo si no había quedado NINGUNA sección
persistida. Con el informe pago (US$ 29), eso deja a un usuario con tres
octavos de informe y sin su crédito. La política nueva cuenta intentos
(`Interpretation.intentos`, `INTENTOS_MAXIMOS`) y, agotados sin completar,
devuelve el crédito, borra la interpretación a medias y avisa — sin mostrar
nunca las secciones sueltas.
"""

import pytest

from api import informe_service
from api import interpretation_service as svc
from api.models import CreditTransaction, Interpretation, InterpretationSection
from interpret.exceptions import InterpretationError
from interpret.prompts import SECCIONES

pytestmark = pytest.mark.django_db


def _generar_solo_tres_secciones(interp):
    """Persiste las tres primeras secciones del catálogo directamente en la
    base, simulando una generación que se cortó a mitad (p. ej. un restart)
    sin pasar por `informe_service.generar_informe`."""
    for orden, seccion in enumerate(SECCIONES[:3]):
        InterpretationSection.objects.create(
            interpretation=interp, slug=seccion.slug, orden=orden,
            texto=f"texto de {seccion.slug}",
        )


class _Stream:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        class R:
            content = [type("B", (), {"type": "text", "text": "una sección"})()]
            stop_reason = "end_turn"

        return R()


class _FakeClient:
    """Cliente Anthropic falso que siempre responde texto fijo: alcanza para
    completar las secciones que falten sin pegarle a la API real."""

    class _M:
        def stream(self, **kw):
            return _Stream()

    @property
    def messages(self):
        return _FakeClient._M()


def _que_siempre_falla(*args, **kwargs):
    """Reemplazo de `informe_service.build_seccion`: cada intento de generar
    cualquier sección de este informe falla, para ejercitar la política de
    intentos agotados sin depender de la API real."""
    raise InterpretationError("el modelo no responde")


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(svc, "_build_client", lambda: _FakeClient())


@pytest.fixture
def build_seccion_falla(monkeypatch):
    monkeypatch.setattr(informe_service, "build_seccion", _que_siempre_falla)


def test_un_informe_a_medias_se_reanuda_sin_cobrar_de_nuevo(make_account, chart, fake_client):
    """Contrapunto de la política de devolución: mientras queden intentos,
    un reintento sobre secciones ya persistidas TERMINA el informe gratis en
    vez de devolver — el crédito ya compró el trabajo, no hay nada que
    reembolsar."""
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    _generar_solo_tres_secciones(interp)
    acc.refresh_from_db()
    assert acc.paid_balance == 0  # ya se cobró al iniciar

    svc.completar_generacion(interp, chart, acc)  # reintento: retoma desde la 4ta sección

    interp.refresh_from_db()
    assert interp.completa is True
    assert interp.secciones.count() == len(SECCIONES)
    acc.refresh_from_db()
    assert acc.paid_balance == 0  # no volvió a cobrar


def test_agotados_los_intentos_devuelve_credito_y_borra_el_informe(
    make_account, chart, build_seccion_falla,
):
    """El corazón de RF21: si el informe nunca se puede completar, después
    de `INTENTOS_MAXIMOS` intentos se devuelve el crédito cobrado y se borra
    la interpretación entera (secciones incluidas) — no queda un informe
    trunco visible ni el crédito perdido."""
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    interp_pk = interp.pk

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    acc.refresh_from_db()
    assert acc.paid_balance == 1  # devuelto
    assert not Interpretation.objects.filter(pk=interp_pk).exists()
    assert not InterpretationSection.objects.filter(interpretation_id=interp_pk).exists()


def test_mientras_quedan_intentos_no_devuelve_ni_borra(make_account, chart, build_seccion_falla):
    """Contrapunto exacto del anterior: con menos intentos que
    `INTENTOS_MAXIMOS`, la fila sigue viva (reanudable) y el crédito sigue
    cobrado — devolver antes de agotar los intentos regalaría el reintento
    Y el crédito."""
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    for _ in range(svc.INTENTOS_MAXIMOS - 1):
        svc.completar_generacion(interp, chart, acc)

    acc.refresh_from_db()
    assert acc.paid_balance == 0  # todavía no se devolvió
    assert Interpretation.objects.filter(pk=interp.pk).exists()
    interp.refresh_from_db()
    assert interp.intentos == svc.INTENTOS_MAXIMOS - 1
    assert interp.completa is False


def test_la_devolucion_no_se_duplica(make_account, chart, monkeypatch, build_seccion_falla):
    """external_id estable por informe (`f"informe:{pk}:devolucion"`), no
    por intento: dos caminos que llegan a devolver el crédito de la MISMA
    interpretación sólo acreditan una vez.

    Para forzar que la rama de devolución se ejecute dos veces sobre la
    MISMA fila (en producción no pasa: `interpretacion.delete()` la saca de
    en medio la primera vez) se neutraliza el `delete()` de esa instancia.
    Si `external_id` incluyera el número de intento en vez de sólo el pk del
    informe, las dos devoluciones generarían claves distintas y las dos
    prosperarían — este test está armado para fallar en ese caso."""
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    monkeypatch.setattr(Interpretation, "delete", lambda self, *a, **kw: None)

    for _ in range(svc.INTENTOS_MAXIMOS + 1):
        svc.completar_generacion(interp, chart, acc)

    acc.refresh_from_db()
    assert acc.paid_balance == 1  # sólo una devolución prosperó
    assert CreditTransaction.objects.filter(kind="adjustment").count() == 1
