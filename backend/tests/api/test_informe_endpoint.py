"""Endpoint del informe: arranca fuera del request y expone su estado.

Task 10: `POST .../interpretation/` deja de generar sincrónicamente (eso
bloqueaba un worker sync de gunicorn durante los ~4 minutos que tarda un
informe de ocho secciones) y pasa a cobrar/crear en el hilo del request pero
generar en uno aparte. `GET .../interpretation/estado` es lo que la web
sondea mientras tanto.
"""

import pytest
from django.core.cache import cache
from django.utils import timezone

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpio():
    """El lock de generación vive en el cache, no en la base: sin esto, el
    hilo de fondo real de `test_el_post_no_espera_a_que_termine` puede seguir
    corriendo (y tomar/soltar el lock) mientras ya arrancó el test siguiente,
    y el `id` de las cartas de fixture se recicla entre tests porque cada uno
    corre en una transacción que se revierte. Mismo patrón que
    `test_interpretation_endpoint.py::_clear_cache`."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _sin_api_key_real(settings):
    """El hilo de fondo no puede pegarle a la API real en un test: si el
    entorno de quien corre pytest tiene un ANTHROPIC_API_KEY de verdad (pasa
    en una sesión de Claude Code, que exporta la suya propia), `_build_client`
    construiría un cliente real y el hilo intentaría una llamada de red de
    verdad. CI nunca tiene esta variable, así que esto sólo importa para
    correr los tests a mano; de cualquier forma no hay que depender de que
    esté ausente."""
    settings.ANTHROPIC_API_KEY = ""


def test_el_post_no_espera_a_que_termine(client_autenticado, chart):
    # Cuatro minutos dentro de la vista bloquean uno de los tres workers sync:
    # tres informes a la vez y el sitio deja de responder.
    r = client_autenticado.post(
        f"/api/charts/{chart.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert r.status_code == 202


def test_el_post_cobra_y_crea_la_interpretacion_pendiente_sincronicamente(client_autenticado, chart, account):
    """La fila y el débito existen apenas responde el 202: si no, un GET a
    /estado inmediatamente después no tendría nada que reportar."""
    from api.models import Interpretation
    from interpret.prompts import PROMPT_VERSION

    antes = account.free_balance + account.paid_balance
    r = client_autenticado.post(
        f"/api/charts/{chart.uuid}/interpretation/", {"lang": "es", "tier": "largo"}, format="json"
    )
    assert r.status_code == 202

    interp = Interpretation.objects.get(chart=chart, lang="es", prompt_version=PROMPT_VERSION)
    assert interp.completa is False
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1


def test_el_estado_dice_cuantas_secciones_van(client_autenticado, chart, interpretacion):
    from api.models import InterpretationSection

    InterpretationSection.objects.create(interpretation=interpretacion, slug="firma", orden=0, texto="x")
    r = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/estado/?tier=largo")
    assert r.json() == {"completa": False, "hechas": 1, "total": 8}


def test_el_estado_sin_interpretacion_todavia_dice_cero(client_autenticado, chart):
    r = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/estado/?tier=largo")
    assert r.json() == {"completa": False, "hechas": 0, "total": 8}


def test_el_estado_sin_tier_es_400(client_autenticado, chart):
    """El tier no tiene default, igual que en el POST: sin él no hay
    catálogo de secciones que calcular (`secciones_aplicables` lo exige)."""
    r = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/estado/")
    assert r.status_code == 400


def test_el_estado_con_lang_invalido_es_400(client_autenticado, chart):
    """Fix wave final / Minor: esta vista era la única de las tres del mismo
    recurso (`InterpretationView.get/post`, `IndiceInformeView.get`) que no
    validaba `lang` — un valor inválido caía derecho a la consulta, no
    encontraba nada, y devolvía 200 con `hechas: 0` como si el informe
    simplemente no hubiera arrancado todavía, en vez de avisar que el
    pedido está mal armado."""
    r = client_autenticado.get(
        f"/api/charts/{chart.uuid}/interpretation/estado/?tier=largo&lang=xx"
    )
    assert r.status_code == 400


def test_el_estado_sin_barra_final_redirige_en_vez_de_404(client_autenticado, chart):
    """HALLAZGO 5 de code review: era la única ruta del archivo sin barra
    final. `APPEND_SLASH` agrega la barra pero nunca la saca, así que un
    cliente que normalizaba a `/estado/` (la forma correcta ahora) recibía
    404 sin redirect. Un cliente viejo que pegue sin la barra sigue
    funcionando: Django lo redirige a la versión canónica."""
    r = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/estado?tier=largo", follow=True)
    assert r.redirect_chain  # hubo un redirect antes de la respuesta final
    assert r.json() == {"completa": False, "hechas": 0, "total": 8}


def test_el_estado_no_mezcla_el_progreso_de_otro_tier(client_autenticado, chart, account):
    """RF9: la breve y el informe completo pueden convivir en la misma carta
    e idioma. Sin filtrar la consulta por tier, `.first()` es determinista
    por pk —encuentra la fila creada primero— así que sondear el estado de
    la breve mientras el informe completo (creado antes) ya está terminado
    devolvía el progreso del producto equivocado: mismo bug de clase que ya
    se había cerrado en el GET de lectura
    (`test_interpretation_get.py::test_con_dos_productos_...`)."""
    from api.models import Interpretation, InterpretationSection
    from interpret.prompts import PROMPT_VERSION, SECCIONES

    largo = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="largo",
        account=account, completa=True,
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(interpretation=largo, slug=seccion.slug, orden=orden, texto="x")

    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="corto",
        account=account, completa=False,
    )

    r = client_autenticado.get(f"/api/charts/{chart.uuid}/interpretation/estado/?lang=es&tier=corto")
    assert r.json() == {"completa": False, "hechas": 0, "total": 1}


def test_lock_tomado_no_genera_ni_cobra_de_nuevo(chart, account, db_cache, monkeypatch):
    """Recupera la cobertura que perdió `test_generation_in_progress_409`
    (retirado en la Task 10, cuando el POST dejó de responder 409
    sincrónico). Con el lock de la carta tomado por otra generación en
    curso, `completar_generacion` no tiene que generar en paralelo —ninguna
    sección tiene protección contra esa carrera, a diferencia de
    `traducir_informe`— ni cobrar de nuevo, eso ya lo resolvió
    `iniciar_generacion`. El test nuevo del POST
    (`test_lock_tomado_no_bloquea_el_202`, en `test_interpretation_endpoint.py`)
    sólo mira el 202, que sale igual con o sin lock porque `iniciar_generacion`
    ni lo consulta: el comportamiento real —justo el bug que motivó el 409
    original— se había quedado sin ningún test.

    db_cache: el lock vive en `DatabaseCache` en producción, no en LocMem.
    """
    from api import interpretation_service as svc, informe_service
    from api.models import Interpretation, InterpretationSection

    llamadas = []
    monkeypatch.setattr(informe_service, "generar_informe", lambda *a, **kw: llamadas.append(1))

    interpretacion = svc.iniciar_generacion(chart, "es", account, tier="largo")
    account.refresh_from_db()
    antes = account.free_balance + account.paid_balance

    cache.add(svc._lock_key(chart, "largo"), "otro-token", timeout=30)

    svc.completar_generacion(interpretacion, chart, account)

    assert llamadas == []  # no generó en paralelo
    assert InterpretationSection.objects.filter(interpretation=interpretacion).count() == 0
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes  # no cobró ni devolvió de nuevo
    assert Interpretation.objects.filter(pk=interpretacion.pk).exists()  # no la tocó


def test_si_la_generacion_muere_el_credito_vuelve(chart, account, monkeypatch):
    """Task 10 / RF21: la devolución ya no es instantánea al primer fallo —
    hace falta agotar `INTENTOS_MAXIMOS` reintentos (cada uno reanuda la
    MISMA `Interpretation`, `iniciar_generacion` no vuelve a cobrar) antes
    de rendirse y devolver."""
    from api import interpretation_service

    def explota(*a, **kw):
        raise RuntimeError("cayó la API")

    monkeypatch.setattr("api.informe_service.generar_informe", explota)
    antes = account.free_balance + account.paid_balance
    for _ in range(interpretation_service.INTENTOS_MAXIMOS):
        interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes


def test_si_la_generacion_gratis_muere_el_credito_vuelve_al_lote_free(chart, account, monkeypatch):
    """BUG 2: `ledger.devolver` fijaba `lot="paid"` siempre, así que un
    informe cobrado de `free_balance` devolvía el crédito a `paid_balance`.
    El test anterior (`test_si_la_generacion_muere_el_credito_vuelve`) sólo
    compara el total y no lo distingue; éste mira cada lote por separado.

    Task 10 / RF21: agota `INTENTOS_MAXIMOS` reintentos antes de esperar la
    devolución (ver el test anterior)."""
    from api import interpretation_service

    def explota(*a, **kw):
        raise RuntimeError("cayó la API")

    monkeypatch.setattr("api.informe_service.generar_informe", explota)
    account.free_balance = 3
    account.paid_balance = 0
    account.save()

    # tier="corto" (Task 6): con el lote atado al tier, un cobro de
    # free_balance sólo puede venir de la lectura breve — el informe
    # completo ("largo") siempre cobra paid_balance, nunca free. Antes de
    # esta tarea cualquier `charge()` podía caer en cualquier lote según el
    # saldo disponible; ahora el lote lo decide el producto pedido.
    for _ in range(interpretation_service.INTENTOS_MAXIMOS):
        interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="corto")

    account.refresh_from_db()
    assert account.free_balance == 3
    assert account.paid_balance == 0


def test_si_la_generacion_paga_muere_el_credito_vuelve_al_lote_paid(chart, account, monkeypatch):
    """Contrapunto del anterior: cobrado de `paid_balance`, tiene que volver
    ahí y no a `free_balance`. Task 10 / RF21: agota los intentos primero
    (ver `test_si_la_generacion_muere_el_credito_vuelve`)."""
    from api import interpretation_service

    def explota(*a, **kw):
        raise RuntimeError("cayó la API")

    monkeypatch.setattr("api.informe_service.generar_informe", explota)
    account.free_balance = 0
    account.paid_balance = 3
    account.save()

    for _ in range(interpretation_service.INTENTOS_MAXIMOS):
        interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="largo")

    account.refresh_from_db()
    assert account.free_balance == 0
    assert account.paid_balance == 3


def test_si_la_generacion_muere_no_queda_una_interpretacion_vacia(chart, account, monkeypatch):
    """Task 10 / RF21: recién al agotar `INTENTOS_MAXIMOS` intentos se borra
    la `Interpretation` — antes de eso sigue viva a propósito, para que el
    siguiente reintento pueda reanudarla sin volver a cobrar."""
    from api.models import Interpretation
    from api import interpretation_service
    from interpret.prompts import PROMPT_VERSION

    monkeypatch.setattr("api.informe_service.generar_informe", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    for _ in range(interpretation_service.INTENTOS_MAXIMOS):
        interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="largo")
    assert not Interpretation.objects.filter(chart=chart, lang="es", prompt_version=PROMPT_VERSION).exists()


def test_si_falla_una_sola_vez_la_interpretacion_sigue_viva_para_reintentar(chart, account, monkeypatch):
    """Contrapunto de `test_si_la_generacion_muere_no_queda_una_interpretacion_vacia`:
    con MENOS fallos que `INTENTOS_MAXIMOS`, la fila no se borra ni se
    devuelve el crédito — sigue reanudable."""
    from api.models import Interpretation
    from api import interpretation_service
    from interpret.prompts import PROMPT_VERSION

    monkeypatch.setattr("api.informe_service.generar_informe", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    antes = account.free_balance + account.paid_balance
    interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1  # sigue cobrado
    assert Interpretation.objects.filter(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, completa=False,
    ).exists()


def test_si_queda_una_seccion_no_se_devuelve_el_credito(chart, account, settings, monkeypatch):
    """Contrapunto del anterior: con una sección persistida el trabajo ya
    está comprado (contrato de `informe_service.generar_informe`); un
    reintento lo completa gratis, no se regala devolviendo el crédito."""
    from api.models import InterpretationSection
    from api import interpretation_service, informe_service

    def falla_despues_de_una_seccion(interpretacion, client, token):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug="firma", orden=0, texto="ya escrita",
        )
        raise RuntimeError("cayó la API a mitad")

    monkeypatch.setattr(informe_service, "generar_informe", falla_despues_de_una_seccion)
    # `_build_client()` se evalúa como argumento ANTES de entrar a
    # `generar_informe` (que acá está mockeado y ni lo mira), así que igual
    # necesita una key no vacía para no explotar antes de llegar al mock.
    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"
    antes = account.free_balance + account.paid_balance
    interpretation_service.generar_en_segundo_plano(chart, "es", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1


# `test_el_cap_diario_cuenta_un_informe_no_ocho_llamadas` (retirado en la
# Task 6): probaba que el cap diario se moviera UNA vez por informe completo
# de ocho secciones, no una vez por llamada al LLM. Con el lote atado al tier
# (RF9, `LOTE_POR_TIER`) esa combinación ya no puede darse: el informe
# completo ("largo") es siempre paid, y paid bypassea el cap por diseño (no
# lo toca en absoluto, ver `iniciar_generacion` — `if lote == "free" and
# ...`), así que un informe de ocho secciones nunca puede tocar el contador.
# La única generación que sí lo toca es la lectura breve ("corto"), que hace
# UNA sola llamada — no hay forma de reproducir "ocho llamadas, un solo
# incremento" bajo el diseño nuevo. Cobertura equivalente sigue viva: que el
# cap se mueve una vez por generación free (no por sección) es una
# consecuencia estructural de dónde vive el incremento (`iniciar_generacion`,
# antes de generar ninguna sección), ya cubierta por
# `test_credits_quota.py::test_paid_generation_bypasses_daily_cap` y
# `test_el_cap_no_se_toca_con_credito_pago` (abajo) para el bypass de paid, y
# por `test_interpretation_service.py::test_daily_cap_blocks_new_generation`
# para el conteo del lote free.


def test_el_cap_no_se_toca_con_credito_pago(account, settings):
    """Bypass del cap para créditos pagos, igual que el flujo viejo de
    interpretación: sólo cuenta generación gratis."""
    from api import interpretation_service as svc
    from api.models import BirthData, Chart

    settings.INTERPRETATION_DAILY_CAP = 0
    cache.clear()
    account.free_balance = 0
    account.paid_balance = 1
    account.save()

    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    chart = Chart.objects.create(birth_data=bd, data={}, engine_version="test", account=account)

    interp = svc.iniciar_generacion(chart, "es", account, tier="largo")
    assert interp is not None
    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    assert cache.get(cap_key) is None


# --- BUG 1: el segundo idioma es una traducción gratis (RF8), no un cobro nuevo ---


def test_iniciar_generacion_no_cobra_si_ya_hay_un_idioma_completo(chart, account, interpretacion_completa):
    """`iniciar_generacion` no había heredado el chequeo de `sibling` que sí
    tenía el flujo viejo de interpretación: cobraba de nuevo por
    cada `(chart, lang)` aunque la carta ya tuviera una lectura completa en
    otro idioma. `interpretacion_completa` ya deja una lectura "es" completa
    sobre `chart`/`account`."""
    from api import interpretation_service as svc

    antes = account.free_balance + account.paid_balance
    svc.iniciar_generacion(chart, "en", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes


def test_iniciar_generacion_cobra_si_no_hay_ningun_idioma_completo(chart, account):
    """Contrapunto: sin ninguna lectura completa todavía, el primer idioma
    sigue cobrando y generando normal."""
    from api import interpretation_service as svc

    antes = account.free_balance + account.paid_balance
    svc.iniciar_generacion(chart, "es", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1


def test_completar_generacion_traduce_el_segundo_idioma_en_vez_de_regenerar(
    chart, account, interpretacion_completa, settings, monkeypatch
):
    """Con un idioma completo ya existente, `completar_generacion` tiene que
    tomar el camino de `informe_service.traducir_informe` (probado en la
    Tarea 9) y no el de `generar_informe`, que le pagaría al modelo ocho
    secciones de nuevo por algo que ya está escrito."""
    from api import interpretation_service as svc, informe_service

    # `_build_client()` se evalúa antes de entrar a las funciones mockeadas.
    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"
    llamadas_generar = []
    llamadas_traducir = []
    monkeypatch.setattr(informe_service, "generar_informe", lambda *a, **kw: llamadas_generar.append(1))
    monkeypatch.setattr(informe_service, "traducir_informe", lambda *a, **kw: llamadas_traducir.append(1))

    svc.generar_en_segundo_plano(chart, "en", account, tier="largo")

    assert llamadas_traducir == [1]
    assert llamadas_generar == []


# --- BUG de la revisión de seguridad: segundo idioma con el primero EN CURSO ---
# `_sibling_completo` sólo mira informes `completa=True`. Pedir "es" y, a
# mitad de sus ~6 minutos de generación, pedir "en" no encontraba sibling
# (el de "es" existe pero no está completo) así que `iniciar_generacion`
# cobraba un segundo crédito para "en". El hilo de "en" llamaba después a
# `completar_generacion`, encontraba el lock de la carta tomado por el hilo
# de "es" y hacía `return` ANTES de su propio `try/finally` — el crédito
# recién cobrado nunca se devolvía. La web promete el segundo idioma gratis
# (`web/lib/i18n.ts`): esto cobraba por algo anunciado como gratis.


def test_pedir_el_segundo_idioma_con_el_primero_en_curso_no_cobra(chart, account, db_cache):
    """Reproduce la secuencia exacta: "es" en curso (lock de la carta
    tomado, fila `completa=False`) y se pide "en". El saldo no puede bajar:
    ni corresponde cobrar un segundo crédito (la carta ya se pagó con "es")
    ni, si se llegara a cobrar, puede perderse sin devolverse."""
    from api import interpretation_service as svc
    from api.exceptions import GenerationInProgress
    from api.models import Interpretation
    from interpret.prompts import PROMPT_VERSION

    interpretacion_es = svc.iniciar_generacion(chart, "es", account, tier="largo")
    assert interpretacion_es.completa is False

    # El hilo de "es" ya tomó el lock de SU tier y sigue generando (igual
    # que haría `completar_generacion` en segundo plano durante ~6 minutos).
    cache.add(svc._lock_key(chart, "largo"), "token-es-en-curso", timeout=600)

    account.refresh_from_db()
    antes = account.free_balance + account.paid_balance

    with pytest.raises(GenerationInProgress):
        svc.iniciar_generacion(chart, "en", account, tier="largo")

    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes  # no se perdió ningún crédito
    assert not Interpretation.objects.filter(
        chart=chart, lang="en", prompt_version=PROMPT_VERSION
    ).exists()  # no queda una fila "en" vacía y cobrada


# --- Fix round 1, Important 1: el lock era por carta, no por (carta, tier) ---
# `_sibling_en_curso` (Task 6) filtra por tier — correcto, un `corto` en
# curso no es sibling de un `largo` en curso, son productos distintos. Pero
# el LOCK que toma `completar_generacion` seguía siendo uno solo por carta
# (`_lock_key` sin tier). Consecuencia: pedir el `corto` mientras el `largo`
# de la MISMA carta y MISMO idioma está en curso no encontraba sibling (tier
# distinto), cobraba el crédito free normal, y al llegar a
# `completar_generacion` chocaba con el lock ajeno del `largo` —
# `got_lock=False`— así que hacía `return` sin generar NI devolver (el
# `finally` sólo calcula `consumo` si `got_lock` es `True`). El crédito
# quedaba cobrado y sin informe, para siempre.


def test_pedir_el_corto_con_el_largo_en_curso_mismo_idioma_no_pierde_el_credito(
    chart, account, db_cache, monkeypatch, settings
):
    """El lock pasa a ser por (chart, tier): dos productos de la misma carta
    se generan en paralelo sin pisarse — son dos pedidos separados del
    usuario, no la misma sección escribiéndose dos veces (eso es lo que el
    lock existe para impedir, y las filas de corto y largo son distintas)."""
    from api import informe_service, interpretation_service as svc
    from api.models import InterpretationSection

    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"

    interpretacion_largo = svc.iniciar_generacion(chart, "es", account, tier="largo")
    assert interpretacion_largo.completa is False

    # El "largo" ya tomó SU lock y sigue generando.
    cache.add(svc._lock_key(chart, "largo"), "token-largo-en-curso", timeout=600)

    account.refresh_from_db()
    antes = account.free_balance + account.paid_balance

    # Mismo idioma, tier distinto: no es sibling (ni completo ni en curso) del
    # largo, así que cobra normal (free) y arranca su propia generación.
    interpretacion_corto = svc.iniciar_generacion(chart, "es", account, tier="corto")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1  # cobró el free normal

    def _generar_fake(interpretacion, client, token):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug="resumen", orden=0, texto="listo",
        )
        interpretacion.text = "listo"
        interpretacion.completa = True
        interpretacion.save(update_fields=["text", "completa"])

    monkeypatch.setattr(informe_service, "generar_informe", _generar_fake)

    svc.completar_generacion(interpretacion_corto, chart, account)

    interpretacion_corto.refresh_from_db()
    # Antes del fix esto daba completa=False para siempre: el lock ajeno del
    # largo bloqueaba al corto, que ni generaba ni devolvía el crédito.
    assert interpretacion_corto.completa is True
    assert interpretacion_corto.secciones.exists()
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes - 1  # el crédito se cobró Y se entregó


# --- HALLAZGO 3 de code review: la devolución infiere "se cobró" en vez de saberlo ---
# La guarda de `completar_generacion` recalculaba `sibling is None` en el
# hilo de fondo — un estado que `iniciar_generacion` ya había decidido antes,
# sobre otra foto de la base. Si `iniciar_generacion` encontró un sibling
# completo (y por eso NO cobró) y ese sibling desaparece antes de que corra
# `completar_generacion`, el recálculo daba `sibling is None`, la generación
# de reemplazo fallaba con 0 secciones, y se acreditaba un crédito por un
# débito que nunca ocurrió.


def test_no_devuelve_credito_si_nunca_se_cobro_aunque_el_sibling_desaparezca(
    chart, account, interpretacion_completa, settings, monkeypatch
):
    """Reproduce la secuencia exacta: `iniciar_generacion` encuentra el
    sibling "es" completo y no cobra por "en" (RF8). El sibling desaparece
    antes de `completar_generacion` (p. ej. se borra esa interpretación) y
    la generación de reemplazo falla sin persistir ninguna sección. El
    saldo no puede bajar: nunca se cobró nada, así que no hay nada que
    devolver.

    Fix wave final / Important: llama a `completar_generacion`
    `INTENTOS_MAXIMOS` veces (no una sola). Con una sola llamada
    `intentos=1 < INTENTOS_MAXIMOS` corta la rama de devolución ANTES de
    llegar a la guarda `consumo is not None` que este test dice proteger —
    pasaba igual aunque se la borrara. Agotando los intentos de verdad, la
    única razón por la que sigue sin devolver es esa guarda."""
    from api import interpretation_service as svc, informe_service

    settings.ANTHROPIC_API_KEY = "sk-test-no-se-usa"
    antes = account.free_balance + account.paid_balance

    interpretacion_en = svc.iniciar_generacion(chart, "en", account, tier="largo")
    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes  # confirmado: no cobró

    interpretacion_completa.delete()  # el sibling desaparece antes de completar_generacion

    def falla_sin_secciones(*a, **kw):
        raise RuntimeError("cayó la API")

    monkeypatch.setattr(informe_service, "generar_informe", falla_sin_secciones)

    for _ in range(svc.INTENTOS_MAXIMOS):
        svc.completar_generacion(interpretacion_en, chart, account)

    account.refresh_from_db()
    assert account.free_balance + account.paid_balance == antes  # nunca se cobró: no hay nada que devolver
