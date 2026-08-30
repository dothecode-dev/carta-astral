"""Task 10 / RF21: o se entrega el informe completo, o se devuelve la plata.

La regla vieja devolvía el crédito sólo si no había quedado NINGUNA sección
persistida. Con el informe pago (US$ 29), eso deja a un usuario con tres
octavos de informe y sin su crédito. La política nueva cuenta intentos
(`Interpretation.intentos`, `INTENTOS_MAXIMOS`) y, agotados sin completar,
devuelve el crédito, borra la interpretación a medias y avisa — sin mostrar
nunca las secciones sueltas.
"""

import pytest
from django.core.cache import cache

from api import informe_service, notificaciones
from api import interpretation_service as svc
from api.models import CreditTransaction, Interpretation, InterpretationSection
from interpret.exceptions import InterpretationError
from interpret.prompts import PROMPT_VERSION, SECCIONES

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
def build_seccion_falla(monkeypatch, settings):
    """El fallo tiene que venir de `build_seccion`, no de `_build_client()`:
    sin una API key en el entorno (el default en tests, salvo que quien
    corre pytest tenga la propia exportada — ver el mismo cuidado en
    `test_informe_endpoint.py::_sin_api_key_real`), `_build_client()`
    revienta ANTES de llegar a `build_seccion` y el mock de abajo queda sin
    ejercitarse: el test pasaría igual, pero no por lo que dice proteger."""
    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"
    monkeypatch.setattr(informe_service, "build_seccion", _que_siempre_falla)


def test_un_informe_a_medias_se_reanuda_sin_cobrar_de_nuevo(make_account, chart, fake_client):
    """Test de REGRESIÓN del comportamiento previo a esta tarea (no de la
    política nueva de intentos: ya pasaba con la guarda vieja de
    `generar_informe`, "reanuda si hay secciones"). Se deja acá porque sigue
    siendo un comportamiento que vale proteger: mientras queden intentos,
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


def test_agotados_los_intentos_devuelve_credito_borra_secciones_y_avisa(
    make_account, chart, build_seccion_falla, monkeypatch,
):
    """El corazón de RF21 — y el escenario exacto que motivó la tarea: un
    usuario que pagó los ocho secciones y se quedó con tres octavos de
    informe. `_generar_solo_tres_secciones` deja esas tres YA persistidas
    (no una fila vacía: si no hubiera nada que borrar, el assert sobre
    `InterpretationSection` de abajo pasaría aunque el cascade no
    funcionara). Con los intentos restantes fallando, agotado
    `INTENTOS_MAXIMOS` se devuelve el crédito cobrado, se borra la
    interpretación ENTERA (las tres secciones ya escritas incluidas — no
    queda un informe trunco visible) y se avisa por
    `api.notificaciones.notificar` con el evento `informe_no_entregado`."""
    avisos = []
    monkeypatch.setattr(
        notificaciones, "notificar",
        lambda account, evento, contexto, lang: avisos.append((account.pk, evento, contexto, lang)),
    )
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    _generar_solo_tres_secciones(interp)
    interp_pk = interp.pk

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    acc.refresh_from_db()
    assert acc.paid_balance == 1  # devuelto
    assert not Interpretation.objects.filter(pk=interp_pk).exists()
    assert not InterpretationSection.objects.filter(interpretation_id=interp_pk).exists()
    assert len(avisos) == 1
    cuenta_avisada, evento, _contexto, _lang = avisos[0]
    assert (cuenta_avisada, evento) == (acc.pk, "informe_no_entregado")


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


def test_traduccion_exitosa_con_intentos_agotados_no_devuelve_ni_borra(
    make_account, chart, build_seccion_falla, monkeypatch,
):
    """Critical de la revisión final: la guarda de devolución miraba
    `interpretacion.completa` EN MEMORIA, que el camino de traducción nunca
    refresca — `informe_service.traducir_informe` resuelve su `destino` con
    un `get_or_create` PROPIO (la MISMA fila por el `unique_together`, pero
    OTRO objeto Python) y escribe `completa=True` ahí, nunca sobre el
    objeto que tiene `completar_generacion`.

    Reproduce la secuencia real: "es" falla generando dos veces (todavía no
    hay sibling en "en"); mientras tanto "en" termina; el tercer intento
    —el que agota `INTENTOS_MAXIMOS`— encuentra ese sibling y TRADUCE CON
    ÉXITO. Eso no puede devolver el crédito ni borrar el informe que se
    acaba de entregar."""
    acc = make_account(free_balance=0, paid_balance=1)
    interp_es = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    # Dos intentos de generación DIRECTA fallan: todavía no existe sibling en "en".
    svc.completar_generacion(interp_es, chart, acc)
    svc.completar_generacion(interp_es, chart, acc)
    interp_es.refresh_from_db()
    assert interp_es.intentos == 2
    assert interp_es.completa is False

    # Mientras tanto, "en" termina (sibling completo: mismo chart y tier).
    interp_en = Interpretation.objects.create(
        chart=chart, lang="en", prompt_version=PROMPT_VERSION,
        tier="largo", account=acc, completa=True,
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interp_en, slug=seccion.slug, orden=orden,
            texto=f"[en] {seccion.slug}",
        )
    monkeypatch.setattr(
        informe_service, "translate_interpretation",
        lambda texto, lang, client: f"[es] {texto}",
    )

    svc.completar_generacion(interp_es, chart, acc)  # 3er intento: encuentra el sibling y traduce

    acc.refresh_from_db()
    assert acc.paid_balance == 0  # sigue cobrado: el informe SE ENTREGÓ, no hay nada que devolver
    assert Interpretation.objects.filter(pk=interp_es.pk).exists()  # no se borró
    interp_es.refresh_from_db()
    assert interp_es.completa is True
    assert interp_es.secciones.count() == len(SECCIONES)


def test_lock_perdido_repetido_no_devuelve_ni_borra(make_account, chart, fake_client, monkeypatch):
    """Important de la revisión final: perder el lock es un aborto LIMPIO
    (`informe_service.generar_informe` devuelve `False`), no un fallo real
    — otro proceso vivo tomó el lock porque el nuestro venció y sigue
    escribiendo esta MISMA interpretación ahora mismo. Contarlo contra
    `INTENTOS_MAXIMOS` podía devolver el crédito y borrar una fila que ese
    otro proceso estaba terminando de verdad.

    Simulamos la pérdida de lock en CADA llamada (`renovar_lock` siempre
    `False`): `INTENTOS_MAXIMOS` abortos así no pueden agotar el contador —
    cada uno se descuenta apenas se detecta."""
    monkeypatch.setattr(informe_service, "renovar_lock", lambda chart, tier, token: False)
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    acc.refresh_from_db()
    assert acc.paid_balance == 0  # sigue cobrado: nunca hubo un fallo real
    assert Interpretation.objects.filter(pk=interp.pk).exists()  # no se borró
    interp.refresh_from_db()
    assert interp.intentos == 0  # cada aborto por lock perdido se descontó
    assert interp.completa is False
    # Cada llamada alcanza a escribir UNA sección más (la de antes de perder
    # el lock) antes de abortar: tres llamadas, tres secciones.
    assert interp.secciones.count() == svc.INTENTOS_MAXIMOS


def test_soltar_lock_no_queda_colgado_si_notificar_revienta(
    make_account, chart, build_seccion_falla, monkeypatch,
):
    """Minor de la revisión final: `soltar_lock` vivía después de
    `notificar` en el `finally` — si `ledger.devolver` o `notificar`
    reventaban, el lock quedaba colgado hasta que venciera el TTL en vez de
    liberarse. Ahora vive en un `finally` interno que corre pase lo que
    pase dentro del bloque de devolución (después de intentar el `delete`,
    no antes: soltarlo antes abriría una ventana para que otro proceso
    tome el lock y escriba sobre una fila que esta misma llamada está por
    borrar)."""
    monkeypatch.setattr(
        notificaciones, "notificar",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("el proveedor de mail está caído")),
    )
    acc = make_account(free_balance=0, paid_balance=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    svc.completar_generacion(interp, chart, acc)
    svc.completar_generacion(interp, chart, acc)
    with pytest.raises(RuntimeError):
        svc.completar_generacion(interp, chart, acc)  # agota los intentos; notificar revienta

    assert cache.get(svc._lock_key(chart, "largo")) is None  # el lock no quedó colgado
    acc.refresh_from_db()
    assert acc.paid_balance == 1  # la devolución ya había corrido antes de que reventara notificar
