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
from api.models import Derecho, Interpretation, InterpretationSection, Movimiento
from interpret.exceptions import InterpretationError
from interpret.prompts import PROMPT_VERSION, SECCIONES

pytestmark = pytest.mark.django_db


def _restante(account, codigo_producto: str) -> int:
    """El saldo que importa es el del `Derecho`: los contadores sueltos que
    tenía `Account` no los tocaba nadie desde el modelo de canje, y la 0025
    los borró. Por cuenta (no global): el fixture `chart` cuelga de
    `account` (conftest), que también fondea su propio derecho, así que más
    de una cuenta puede tener un `Derecho` con el mismo `codigo_producto`
    en el mismo test."""
    return Derecho.objects.get(account=account, codigo_producto=codigo_producto).cantidad_restante


@pytest.fixture(autouse=True)
def _cache_limpio():
    """El lock de generación (`interp:lock:*`) vive en el cache de Django,
    que es GLOBAL AL PROCESO de test —LocMemCache no se resetea entre
    archivos ni entre tests salvo que alguien lo limpie explícitamente— no
    en la base, que sí se revierte por test. Mismo patrón que
    `test_informe_endpoint.py::_cache_limpio` y
    `test_interpretation_service.py::_clear_cache`: sin esto, un lock que
    otro archivo deja tomado (por la razón que sea) puede envenenar estos
    tests, y viceversa. La causa real de que esto se manifestara una vez
    (`test_delete_charts_preserva_ledger` dejaba un lock colgado por una
    excepción no capturada) ya se corrigió en `completar_generacion`; esto
    es la segunda red, no la primera."""
    cache.clear()
    yield
    cache.clear()


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
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    _generar_solo_tres_secciones(interp)
    assert _restante(acc, "informe_natal") == 0  # ya se cobró al iniciar

    svc.completar_generacion(interp, chart, acc)  # reintento: retoma desde la 4ta sección

    interp.refresh_from_db()
    assert interp.completa is True
    assert interp.secciones.count() == len(SECCIONES)
    assert _restante(acc, "informe_natal") == 0  # no volvió a cobrar


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
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    _generar_solo_tres_secciones(interp)
    interp_pk = interp.pk

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    assert _restante(acc, "informe_natal") == 1  # devuelto
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
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    for _ in range(svc.INTENTOS_MAXIMOS - 1):
        svc.completar_generacion(interp, chart, acc)

    assert _restante(acc, "informe_natal") == 0  # todavía no se devolvió
    assert Interpretation.objects.filter(pk=interp.pk).exists()
    interp.refresh_from_db()
    assert interp.intentos == svc.INTENTOS_MAXIMOS - 1
    assert interp.completa is False


def test_la_devolucion_no_se_duplica(make_account, chart, monkeypatch, build_seccion_falla):
    """Dos caminos que llegan a devolver el derecho de la MISMA interpretación
    sólo acreditan una vez.

    Para forzar que la rama de devolución se ejecute dos veces sobre la
    MISMA fila (en producción no pasa: `interpretacion.delete()` la saca de
    en medio la primera vez) se neutraliza el `delete()` de esa instancia.

    Task 11: la doble protección ya no depende sólo del `external_id`
    estable (`f"informe:{pk}:devolucion"`, que `canje.devolver` sigue
    respetando) — la guarda de `completar_generacion` misma deja de
    intentarlo: `devolver` desvincula el `Movimiento` de consumo de esta
    carta (`chart=None`) al acreditar, así que la SEGUNDA vuelta ya no
    encuentra un consumo vigente para esta carta y ni siquiera llama a
    `devolver` de nuevo. Cualquiera de las dos protecciones alcanza para
    que esto pase; lo que importa es el resultado observable: una sola
    devolución."""
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    monkeypatch.setattr(Interpretation, "delete", lambda self, *a, **kw: None)

    for _ in range(svc.INTENTOS_MAXIMOS + 1):
        svc.completar_generacion(interp, chart, acc)

    assert _restante(acc, "informe_natal") == 1  # sólo una devolución prosperó
    assert Movimiento.objects.filter(codigo_producto="informe_natal", tipo="devolucion").count() == 1


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
    acc = make_account(lecturas_breves=0, informes=1)
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

    assert _restante(acc, "informe_natal") == 0  # sigue cobrado: el informe SE ENTREGÓ, no hay nada que devolver
    assert Interpretation.objects.filter(pk=interp_es.pk).exists()  # no se borró
    interp_es.refresh_from_db()
    assert interp_es.completa is True
    assert interp_es.secciones.count() == len(SECCIONES)


def test_traduccion_a_un_tercer_idioma_que_falla_no_devuelve_lo_ya_entregado(
    make_account, chart, settings, monkeypatch,
):
    """Task 11, fix round 1 (Important 2): el caso que motivó ampliar
    `completo_ahora` de "esta interpretación" a "cualquier idioma de esta
    carta y tier".

    Con la guarda vieja (una `CreditTransaction` por `Interpretation`,
    Task 10) esto ya estaba resuelto por otro lado: `consumo` daba `None`
    para una traducción que nunca se cobró, así que nunca llegaba a mirar
    `completo_ahora`. Con la guarda nueva (Task 11: un `Movimiento` por
    `(chart, tier)`, no por fila — `canje.canjear` compra por carta+tier,
    no por idioma) el `Movimiento` del idioma que SÍ se cobró ("es") sigue
    vinculado a esta carta, así que `consumo` da `True` TAMBIÉN para "pt".
    Si `completo_ahora` mirara sólo `interpretacion.pk` (la fila de "pt",
    que nunca se completa porque la traducción siempre falla), esto
    devolvería el derecho de una carta que YA se entregó —en "es"— sólo
    porque la traducción gratis a un TERCER idioma nunca prospera. Mirar
    "cualquier idioma de esta carta y tier" es lo que cierra ese hueco."""
    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"
    acc = make_account(lecturas_breves=0, informes=1)

    # "es" se cobra y se entrega de verdad: es el único Movimiento de
    # consumo que existe para esta carta y tier.
    interp_es = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    interp_es.completa = True
    interp_es.save(update_fields=["completa"])
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interp_es, slug=seccion.slug, orden=orden,
            texto=f"[es] {seccion.slug}",
        )
    assert _restante(acc, "informe_natal") == 0  # se cobró al pedir "es"

    # "pt" encuentra a "es" como sibling completo: no cobra nada (RF8), y
    # su único camino es traducir — que en este test SIEMPRE falla.
    interp_pt = svc.iniciar_generacion(chart, "pt", acc, tier="largo")
    assert _restante(acc, "informe_natal") == 0  # "pt" no cobró nada

    monkeypatch.setattr(
        informe_service, "translate_interpretation",
        lambda texto, lang, client: (_ for _ in ()).throw(InterpretationError("no traduce")),
    )

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp_pt, chart, acc)

    # La carta YA entregó lo que se cobró (en "es"): no hay nada que
    # devolver aunque la traducción gratis a "pt" nunca prospere.
    assert _restante(acc, "informe_natal") == 0
    assert Interpretation.objects.filter(pk=interp_pt.pk).exists()  # no se borró
    interp_pt.refresh_from_db()
    assert interp_pt.completa is False


def test_devuelve_si_ningun_idioma_de_la_carta_y_tier_se_entrego(make_account, chart, build_seccion_falla):
    """Contrapunto de la anterior (Task 11, fix round 1): que
    `completo_ahora` mire "cualquier idioma de esta carta y tier" no puede
    aflojar la guarda al punto de no devolver nunca. Acá hay DOS filas para
    la misma carta y tier —"es", la que se reintenta, y "en", que quedó a
    medias de otro pedido— y NINGUNA está completa: la sola EXISTENCIA de
    un sibling no alcanza para frenar la devolución, hace falta que esté
    COMPLETO (ver el test de arriba, donde si lo está)."""
    acc = make_account(lecturas_breves=0, informes=1)
    interp_es = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    # Otro idioma de la MISMA carta y tier, a medias: existe como fila pero
    # no debe fingir que la carta ya se entregó en ningún idioma.
    Interpretation.objects.create(
        chart=chart, lang="en", prompt_version=PROMPT_VERSION,
        tier="largo", account=acc, completa=False,
    )

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp_es, chart, acc)

    assert _restante(acc, "informe_natal") == 1  # devuelto: la carta nunca se entregó en ningún idioma
    assert not Interpretation.objects.filter(pk=interp_es.pk).exists()


def test_no_devuelve_si_hay_una_fila_completa_en_otro_prompt_version(make_account, chart, build_seccion_falla):
    """Fix round 2 (Important 2): `completo_ahora` no puede filtrar por
    `prompt_version` — `consumo` tampoco lo hace (el `Movimiento` no tiene
    ese campo; la compra es por chart+tier, no por chart+tier+versión del
    prompt), y esa asimetría regalaba un informe.

    Reproduce el escenario real: alguien paga y recibe "es" con una versión
    VIEJA del prompt; se bumpea `PROMPT_VERSION`; vuelve a pedir "es" —
    `canjear` hace no-op (mismo chart+tier ya cobrado, `Movimiento` sin
    campo de versión, no hay doble cobro) pero esa fila nueva, en la
    versión ACTUAL, falla siempre y agota los intentos. El cobro real se
    hace con `canje.canjear` directo (no con `iniciar_generacion`, que
    siempre crea con la versión ACTUAL del módulo — no serviría para dejar
    una fila completa en una versión distinta) y las dos filas se arman a
    mano para poder fijar cada `prompt_version` por separado.

    Con el filtro viejo (`prompt_version=PROMPT_VERSION` en `completo_
    ahora`, que compara contra la versión ACTUAL, no contra la de
    `interpretacion`) la fila vieja quedaba invisible pese a estar
    completa y entregada, y esto devolvía un derecho nunca cobrado además
    de desvincular el consumo real, dejando la carta como "no comprada"."""
    from api.canje import canjear

    acc = make_account(lecturas_breves=0, informes=1)

    # Se cobra de verdad (Movimiento real, vinculado a esta carta) y se
    # entrega con una versión VIEJA del prompt.
    canjear(acc, "leer_informe", chart)
    interp_vieja = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version="prompt-version-vieja",
        tier="largo", account=acc, completa=True,
    )
    assert _restante(acc, "informe_natal") == 0  # se cobró

    # Fila nueva de la MISMA carta y tier, en la versión ACTUAL del
    # prompt —lo que habría dejado `iniciar_generacion` tras el no-op de
    # `canjear` si `PROMPT_VERSION` se hubiera bumpeado de verdad.
    interp_nueva = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION,
        tier="largo", account=acc, completa=False,
    )

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp_nueva, chart, acc)

    # No se devuelve nada: el chart+tier YA se entregó (con la versión
    # vieja del prompt), y el `Movimiento` de consumo real sigue vinculado
    # a esta carta.
    assert _restante(acc, "informe_natal") == 0
    assert Interpretation.objects.filter(pk=interp_vieja.pk).exists()


def test_la_devolucion_acredita_el_producto_real_no_una_constante_por_tier(
    make_account, chart, build_seccion_falla, monkeypatch,
):
    """Fix round 2 (Important 1): `codigo` se lee del `Movimiento` de
    consumo real, no se re-deriva de una constante tier→producto
    (`CODIGO_POR_TIER`, ya retirada). Con el catálogo real de hoy esto no
    se puede distinguir de la constante vieja: `informe_natal` y
    `pack_5_natal` acreditan el mismo código al otorgar. Se inyecta acá un
    segundo producto que da la MISMA capacidad (`leer_informe`) pero
    acredita OTRO código —el caso real que el catálogo va a tener el día
    que exista un vínculo, un año o una suscripción— con el mismo patrón
    que ya usa el resto de la suite de canje (`test_canje_puede.py`,
    `test_canje_otorgar.py`): `monkeypatch.setitem(catalogo.CATALOGO,
    ...)`. `productos_con_capacidad` lee el diccionario del módulo en cada
    llamada, así que la inyección funciona sin importar cómo la importe
    `interpretation_service`.

    Con la constante vieja (fija en "informe_natal" para tier="largo") la
    cuenta de este test —que sólo tiene un derecho de "informe_vinculo",
    nunca "informe_natal"— no deja ver el `Movimiento` real: la guarda de
    devolución no encuentra consumo que devolver y no acredita nada, dejando
    a la cuenta sin el derecho que sí pagó y sin el informe que nunca
    recibió."""
    from api import catalogo
    from api.canje import otorgar

    monkeypatch.setitem(catalogo.CATALOGO, "informe_vinculo", catalogo.Producto(
        codigo="informe_vinculo", precio_centavos=3900, naturaleza=catalogo.CONSUMIBLE,
        capacidades=("leer_informe",), otorga=("informe_vinculo", 1),
    ))

    acc = make_account(lecturas_breves=0, informes=0)
    otorgar(acc, "informe_vinculo", 1, origen="compra", external_id="test:vinculo")

    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")
    assert _restante(acc, "informe_vinculo") == 0  # se cobró de verdad

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    assert _restante(acc, "informe_vinculo") == 1  # devuelto al producto real
    assert not Interpretation.objects.filter(pk=interp.pk).exists()


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
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interp, chart, acc)

    assert _restante(acc, "informe_natal") == 0  # sigue cobrado: nunca hubo un fallo real
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
    `notificar` en el `finally` — si `devolver` o `notificar`
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
    acc = make_account(lecturas_breves=0, informes=1)
    interp = svc.iniciar_generacion(chart, "es", acc, tier="largo")

    svc.completar_generacion(interp, chart, acc)
    svc.completar_generacion(interp, chart, acc)
    with pytest.raises(RuntimeError):
        svc.completar_generacion(interp, chart, acc)  # agota los intentos; notificar revienta

    assert cache.get(svc._lock_key(chart, "largo")) is None  # el lock no quedó colgado
    assert _restante(acc, "informe_natal") == 1  # la devolución ya había corrido antes de que reventara notificar
