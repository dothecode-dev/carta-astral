"""Orquestación de la interpretación.

Cache en DB (fuente de verdad) + tope global diario + lock de concurrencia,
todo sobre django.core.cache. Construye el cliente Anthropic desde settings y
se lo inyecta a interpret/ (que no toca settings ni la API key).
"""

import hashlib
import json
import logging
import uuid

import anthropic
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from api import ledger, notificaciones
from api.canje import SinDerecho, canjear, devolver
from api.exceptions import CapReached, GenerationInProgress
from api.models import Interpretation, Movimiento
from interpret.exceptions import InterpretationError
from interpret.prompts import PROMPT_VERSION, TIER_CORTO, TIER_LARGO

# Qué capacidad cobra cada tier (RF9 dos tiers, Task 11 modelo de canje): la
# lectura breve canjea la capacidad regalada, el informe completo la capacidad
# paga. Con dos productos la capacidad ES el producto — de acá sale lo que
# `canje.canjear` busca entre los derechos de la cuenta.
CAPACIDAD_POR_TIER = {TIER_CORTO: "leer_breve", TIER_LARGO: "leer_informe"}

# Qué producto se acredita al devolver, por tier: tiene que ser el mismo
# producto del que se cobró (mismo motivo que documentaba `ledger.devolver`
# sobre el lote — devolver al producto equivocado descuadra la conciliación).
CODIGO_POR_TIER = {TIER_CORTO: "lectura_breve", TIER_LARGO: "informe_natal"}

# Import diferido (no al tope del módulo): `informe_service` importa
# `renovar_lock` DESDE acá, así que un `import` a nivel de módulo en ambas
# direcciones sería circular. `generar_en_segundo_plano` lo importa recién al
# llamarse.

logger = logging.getLogger(__name__)

# Ocho secciones a ~30-45 s cada una. El valor viejo (30 s) soltaba el candado
# mientras el informe se seguía escribiendo, y dos pestañas generaban el mismo
# informe dos veces cobrando dos créditos.
LOCK_TTL = 600

# RF21: cuántas veces `completar_generacion` reintenta un informe incompleto
# antes de rendirse. El dueño del producto lo decidió así: si no se puede
# entregar el informe de ocho secciones que se cobró entero, se devuelve el
# crédito y no se muestran las secciones sueltas — un informe de US$ 29 no
# es como la lectura gratis que originó la regla vieja ("devolvé sólo si no
# quedó nada"), donde un informe trunco no le costaba nada al usuario.
INTENTOS_MAXIMOS = 3

DISCLAIMERS = {
    "es": "Esta interpretación fue generada con inteligencia artificial con fines "
    "de entretenimiento; no es consejo médico, legal ni financiero y no tiene "
    "valor predictivo demostrado.",
    "en": "This interpretation was generated with artificial intelligence for "
    "entertainment purposes; it is not medical, legal or financial advice and "
    "has no demonstrated predictive value.",
    "pt": "Esta interpretação foi gerada com inteligência artificial para fins "
    "de entretenimento; não é conselho médico, legal ou financeiro e não tem "
    "valor preditivo comprovado.",
}


def credits_available(account) -> int:
    return ledger.credits_available(account)


def _build_client():
    if not settings.ANTHROPIC_API_KEY:
        # Sin key el SDK lanza TypeError (500 crudo); mejor un 503 prolijo.
        raise InterpretationError("ANTHROPIC_API_KEY no configurada")
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, timeout=25.0)


def _seconds_until_midnight() -> int:
    now = timezone.now()
    tomorrow = (now + timezone.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((tomorrow - now).total_seconds())


def _lock_key(chart, tier: str) -> str:
    # Por (chart, tier), no sólo por chart (fix round 1, Important 1): el
    # corto y el largo de la misma carta son dos `Interpretation` distintas
    # (RF9, cada una con su propio set de secciones) que un usuario puede
    # pedir por separado y esperar que avancen en paralelo — hacer esperar
    # al que pagó US$ 29 mientras corre la lectura gratis (o viceversa)
    # sería peor que la carrera que el lock existe para evitar, que es dos
    # procesos escribiendo LAS MISMAS secciones. Con un lock compartido entre
    # tiers, `completar_generacion` del segundo tier pedido encontraba el
    # lock del primero tomado, hacía `return` con `got_lock=False` y ni
    # generaba ni devolvía el crédito ya cobrado por `iniciar_generacion`
    # — quedaba cobrado y sin informe, para siempre.
    return f"interp:lock:{chart.id}:{PROMPT_VERSION}:{tier}"


def renovar_lock(chart, tier: str, token: str) -> bool:
    """Repone el TTL del lock de esta carta y este tier mientras hay progreso real.

    Un informe son ocho llamadas secuenciales al LLM: la Tarea 6 llama a esto
    después de persistir cada sección para que el lock nunca expire en medio
    de una generación en curso. Recibe el token que devolvió `tomar_lock` al
    tomarlo: sólo renueva si el valor guardado en la clave todavía es ESE
    token, nunca "el lock que haya".

    `touch()` no chequea expiración por sí solo (sólo `add` lo hace, en
    `_base_set`): sobre `DatabaseCache` puede resucitar 600 s una fila vencida
    que el purgado todavía no borró. Por eso el chequeo es con `get()`
    primero: sobre `DatabaseCache` un `get()` de una clave vencida devuelve
    `None` y purga la fila al pasar, que es la comprobación de expiración que
    a `touch()` le falta. Queda una ventana de microsegundos entre el `get` y
    el `touch` donde la clave podría vencer o cambiar de dueño justo en el
    medio; el peor caso ahí es extender un lock propio recién vencido, nunca
    resucitar ni pisar el de otro proceso.
    """
    key = _lock_key(chart, tier)
    if cache.get(key) != token:
        return False
    return bool(cache.touch(key, LOCK_TTL))


def soltar_lock(chart, tier: str, token: str) -> None:
    """Libera el lock de esta carta y este tier sólo si sigue siendo el propio.

    Sin este chequeo, un proceso cuyo lock ya expiró y fue tomado por otro
    borraría el lock ajeno al terminar (o fallar) tarde. Mismo principio que
    `renovar_lock`: nunca tocar una clave cuyo token no es el nuestro.
    """
    key = _lock_key(chart, tier)
    if cache.get(key) == token:
        cache.delete(key)


def _sibling_completo(chart, lang: str, tier: str) -> Interpretation | None:
    """Informe COMPLETO de esta misma carta, MISMO tier, en otro idioma, si existe.

    Es el mismo criterio del flujo viejo de interpretación (RF8: un crédito
    por carta, no por idioma) adaptado al flujo de la Tarea 10: acá `completa`
    hace falta porque `iniciar_generacion` deja una fila vacía
    (`completa=False`) apenas arranca, y esa fila en curso no sirve como
    fuente de traducción ni cuenta como "ya pagado" — todavía no hay texto
    que traducir. `iniciar_generacion` la usa para decidir si cobra;
    `completar_generacion` la vuelve a evaluar para decidir si traduce en vez
    de generar. Recalcularla en vez de pasarla entre ambas evita acoplar sus
    firmas al resultado de la otra, a costa de una consulta extra barata.

    El filtro por `tier` (Task 6, RF9) es lo que evita regalar el informe
    completo: una lectura breve en español no es sibling de un informe
    completo en inglés — son productos distintos, no traducciones uno del
    otro. Sin este filtro, pedir la breve en "en" después de tener el
    completo en "es" encontraría ese completo como sibling y lo entregaría
    gratis en vez de cobrar el crédito free que corresponde."""
    return (
        Interpretation.objects.filter(
            chart=chart, prompt_version=PROMPT_VERSION, tier=tier, completa=True,
        )
        .exclude(lang=lang)
        .first()
    )


def _sibling_en_curso(chart, lang: str, tier: str) -> Interpretation | None:
    """Informe de esta misma carta en OTRO idioma que ya arrancó pero
    todavía no terminó (`completa=False`).

    BUG de la revisión de seguridad: `iniciar_generacion` sólo consultaba
    `_sibling_completo` (arriba), que exige `completa=True`. Pedir "es" y, a
    mitad de sus ~6 minutos de generación, pedir "en" no encontraba sibling
    —el de "es" existe pero no está completo— así que cobraba un segundo
    crédito para "en". El hilo de "en" llamaba después a
    `completar_generacion`, encontraba el lock de la carta (compartido por
    todos los idiomas, ver `_lock_key`) tomado por el hilo de "es", y hacía
    `return` sin generar nada: el crédito recién cobrado quedaba perdido —la
    web promete el segundo idioma gratis (`web/lib/i18n.ts`).

    La corrección va acá y no en `completar_generacion` porque el problema
    es cobrar, no dejar de devolver: mientras exista un sibling en curso, no
    hay nada que traducir todavía (no como `_sibling_completo`) y tampoco
    conviene generar un informe independiente para "en" —eso pagaría dos
    veces por la misma carta, violando RF8 apenas "es" termine y sea gratis
    para traducir. `iniciar_generacion` rechaza el pedido en vez de cobrar y
    esperar: no hay una cola ni un job que retome el pedido de "en" solo,
    así que "esperar" significaría un 202 fantasma que nunca progresa.
    Rechazar con un estado claro (`GenerationInProgress`, ya usado
    por el flujo viejo de interpretación en este mismo caso) es
    lo que la web ya sabe interpretar como "reintentá en unos segundos"
    (ver `web/app/api/charts/[id]/interpretation/route.ts`, que traduce un
    409 del backend a ese mensaje).

    Deja una ventana de carrera microscópica frente a `_sibling_completo`
    (dos consultas separadas, no una transacción): si "es" termina justo
    entre ambas, esta consulta ya no lo ve (pasó a `completa=True`) y
    "en" cobra y genera desde cero en vez de traducir gratis. No es el bug
    reportado (que es una espera de minutos, no de microsegundos) y no
    pierde plata —cobra una vez, igual que si no hubiera sibling—, así que
    no amerita la complejidad de una transacción con lock de fila.

    HALLAZGO 2 de code review (informe-natal): esta función no tenía límite
    de antigüedad — CUALQUIER fila `completa=False` bloqueaba el resto de
    los idiomas de esa carta con 409 para siempre, sin salida. Y quedan así
    fácil: un restart de gunicorn a mitad de generación, o el techo de
    tokens del HALLAZGO 1 (`interpret/generator.py`), dejan una fila
    `completa=False` cuyo proceso ya no existe.

    Criterio elegido: lock VIVO. El lock de la carta (`_lock_key`, con TTL y
    dueño vía `renovar_lock`/`soltar_lock`, todos en este mismo módulo) es
    justo la señal de "hay un proceso generando esto ahora mismo" que ya
    existe y ya está tuneada (`LOCK_TTL` cubre las ocho llamadas de un
    informe). Sin lock vivo no hay nadie escribiendo esta carta —ni "es" va
    a progresar más— así que bloquear otro idioma no evita ningún trabajo
    duplicado, sólo deja al usuario sin salida. Se prefirió sobre una
    antigüedad fija (`created_at`/`updated_at`) porque el lock ya captura
    "vivo" con precisión (se renueva sección a sección) en vez de una
    ventana de tiempo arbitraria que sería demasiado corta para un informe
    lento o demasiado larga para uno realmente abandonado.

    Nota: en el caso de un restart de gunicorn a mitad de generación, el
    lock sigue vivo hasta que expira su TTL (hasta `LOCK_TTL` segundos) —
    ese informe abandonado todavía bloquea otros idiomas por esa ventana,
    después dejar de hacerlo solo. Es el mismo comportamiento que ya tiene
    el resto del módulo (nada purga el lock antes de su TTL) y no es peor
    que antes: antes bloqueaba para SIEMPRE.

    El filtro por `tier` (Task 6, RF9) es el mismo que en `_sibling_completo`
    y por la misma razón: una lectura breve en curso no es sibling de un
    informe completo en curso en otro idioma, son productos distintos. El
    lock que se consulta acá es el del MISMO tier (`_lock_key(chart, tier)`,
    fix round 1): el lock es por (chart, tier) desde que dos tiers de la
    misma carta pueden generarse en paralelo — mirar el lock de OTRO tier
    acá no diría nada sobre si hay una generación en curso de ESTE."""
    if cache.get(_lock_key(chart, tier)) is None:
        return None
    return (
        Interpretation.objects.filter(
            chart=chart, prompt_version=PROMPT_VERSION, tier=tier, completa=False,
        )
        .exclude(lang=lang)
        .first()
    )


def content_key(chart_data: dict, lang: str, prompt_version: str, tier: str) -> str:
    """Hash canónico del input del LLM, incluyendo el tier del producto.
    Dos cartas con el mismo JSON astrológico (mismo instante UTC, lugar,
    house system, engine) Y el mismo tier pueden reutilizar lectura; tiers
    distintos generan hashes distintos. Esto previene que un informe completo
    pagado reciba el texto de una lectura breve de otra carta con los mismos
    datos de nacimiento.

    INACTIVA: ningún camino la llama desde que el informe se genera por
    secciones (28-08-2026); las filas nuevas quedan con `content_key=""`.
    """
    canonical = json.dumps(chart_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{prompt_version}:{lang}:{tier}:{canonical}".encode()).hexdigest()


def iniciar_generacion(chart, lang: str, account, tier: str) -> Interpretation:
    """Crea (o recupera) la `Interpretation` de un informe y cobra si
    corresponde. Corre siempre en el hilo del request —nunca en el hilo de
    fondo—: es lo que le permite a la vista responder 402/503 sincrónicamente
    en vez de aceptar un 202 que después nunca va a completarse.

    `tier` no tiene default (Task 6, RF9, mismo criterio que
    `informe_service.secciones_aplicables`): un default silencioso
    convertiría "me olvidé de pasar el tier" en "le cobro/entrego el
    producto equivocado" en vez de un `TypeError` inmediato. Decide, vía
    `CAPACIDAD_POR_TIER`, qué capacidad se canjea — leer_breve para la
    lectura breve, leer_informe para el informe completo (Task 11) —
    porque con dos productos la capacidad ES el producto: canjear la otra
    sería cobrar el que no corresponde.

    Usa `get_or_create` (no un lock) para la creación: Django envuelve su
    `create()` en `atomic()` y reconsulta ante un choque de
    `unique_together`, así que sólo UNA llamada concurrente gana `created`
    (mismo mecanismo que ya validó la Tarea 9 para `traducir_informe`). Sólo
    esa llamada cobra; la que pierde la carrera devuelve la fila existente
    sin tocar los derechos. El lock de `_lock_key` es para otra cosa —serializar
    la GENERACIÓN de secciones sobre una misma carta— y lo toma quien sigue
    con `completar_generacion`, no esta función.

    El cap diario cuenta INFORMES, no llamadas al modelo: se incrementa acá,
    una vez por `Interpretation` nueva pagada con crédito gratis, y no en
    `informe_service.generar_informe` (que hace ocho llamadas por informe).
    Con el cap actual (40) eso da ~40 informes/día × US$0.45 ≈ US$18/día; si
    contara las ocho llamadas el mismo cap alcanzaría para 5 informes por día
    y el producto se apagaría a media mañana.

    Lanza `SinDerecho` o `CapReached` si corresponde, y en ese caso borra
    la `Interpretation` vacía que `get_or_create` acababa de crear: si
    quedara, una llamada posterior (con crédito ya disponible) la
    encontraría con `created=False` y jamás cobraría nada.

    RF8 / BUG de la revisión final: esta función no heredaba el chequeo de
    `sibling` que sí tenía el flujo viejo de interpretación, y
    cobraba un crédito nuevo por cada `(chart, lang)` aunque la carta ya
    tuviera una lectura completa en otro idioma — la web promete lo
    contrario. Con `_sibling_completo` encontrado, el segundo idioma no cobra
    ni cuenta contra el cap: `completar_generacion` va a traducir ese sibling
    en vez de generar desde cero.

    RF8 / BUG de la revisión de seguridad: `_sibling_completo` no alcanza —
    exige `completa=True`, y el caso real es uno EN CURSO. Pedir "es" y, a
    mitad de sus ~6 minutos, pedir "en" no encontraba sibling completo,
    cobraba igual, y ese crédito se perdía cuando el hilo de "en" chocaba
    contra el lock que "es" todavía tenía tomado (ver `_sibling_en_curso`
    para el detalle y la justificación de por qué se rechaza acá en vez de
    esperar). Se lanza `GenerationInProgress` ANTES de cobrar: no hay nada
    que devolver porque nunca se llega a tocar ningún derecho."""
    interpretacion, creada = Interpretation.objects.get_or_create(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION, tier=tier,
        defaults={"text": "", "account": account},
    )
    if not creada:
        return interpretacion

    if _sibling_completo(chart, lang, tier) is not None:
        return interpretacion

    if _sibling_en_curso(chart, lang, tier) is not None:
        interpretacion.delete()
        raise GenerationInProgress(
            "hay una generación en curso para esta carta en otro idioma, "
            "reintentá en unos segundos"
        )

    capacidad = CAPACIDAD_POR_TIER[tier]
    # El cap diario protege el gasto de LLM sin ingreso: aplica sólo a lo
    # regalado, que es exactamente la lectura breve (Task 11). Un cap
    # pensado para eso no puede frenar un informe que alguien pagó — antes
    # de esta tarea se gateaba con `lote == "free"`, mismo criterio, sin
    # tener que adivinar de qué lote *iba* a cobrarse.
    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    if capacidad == "leer_breve" and cache.get(cap_key, 0) >= settings.INTERPRETATION_DAILY_CAP:
        interpretacion.delete()
        logger.warning(
            "interpretation daily cap reached (cap=%s)", settings.INTERPRETATION_DAILY_CAP
        )
        raise CapReached()

    try:
        canjear(account, capacidad, chart, build=lambda: interpretacion)
    except SinDerecho:
        interpretacion.delete()
        raise

    if capacidad == "leer_breve":
        cache.add(cap_key, 0, timeout=_seconds_until_midnight())
        cache.incr(cap_key)
    return interpretacion


def completar_generacion(interpretacion: Interpretation, chart, account) -> None:
    """Toma el lock de la carta y corre `informe_service.generar_informe`
    hasta terminar o fallar; al final liquida el crédito.

    Pensada para correr en un hilo aparte del request (la vista la lanza así
    para no bloquear un worker sync durante los ~4 minutos que tarda un
    informe), pero no asume threading: es una función común, y
    `generar_en_segundo_plano` la llama sincrónicamente para los casos (tests,
    reintentos internos) que necesitan el resultado ya liquidado al volver.

    El lock es el único mecanismo de exclusión (no se inventa un segundo): si
    ya está tomado, asumimos que otro proceso está generando esta misma carta
    y no hacemos nada — ni cobramos de nuevo (eso ya lo resolvió
    `iniciar_generacion`), ni generamos en paralelo (eso duplicaría secciones
    y ninguna sección tiene protección contra esa carrera, a diferencia de
    `traducir_informe`).

    Nunca deja una excepción sin loguear: si el hilo de fondo muere en
    silencio, el informe queda colgado con el crédito ya cobrado y nadie se
    entera hasta que el usuario se queja.

    Si ya existe un informe completo de esta carta en otro idioma
    (`_sibling_completo`), traduce ese informe (`informe_service.
    traducir_informe`, Tarea 9) en vez de generar desde cero: es gratis (RF8,
    ya lo decidió `iniciar_generacion` no cobrando) y evita pagarle al modelo
    ocho secciones que ya existen en otro idioma. El lock es el mismo en
    ambos caminos — se toma acá antes de saber cuál toca — así que la
    traducción queda serializada contra otra generación de la misma carta
    igual que la generación.

    El chequeo `if not got_lock: return` vive ANTES del `try/finally` desde
    la wave de fix final (post-review) — hasta ahí vivía DENTRO, porque la
    revisión de seguridad había encontrado que un `return` temprano por
    fuera del bloque protegido salteaba el `finally` que devuelve el
    crédito. Eso seguía siendo cierto para un `return` que saltee trabajo
    hecho CON el lock tomado; no aplica acá: `got_lock=False` significa que
    esta llamada NUNCA tomó el lock (otro proceso lo tiene), así que no hay
    nada que esta llamada haya cobrado, generado ni tomado que necesite
    limpieza — es exactamente el caso que el propio código viejo ya
    señalaba como "no hace nada" en su `finally`. Sacarlo afuera simplifica
    todo lo que sigue: dentro del `try/finally` de acá abajo `got_lock` es
    SIEMPRE `True`, así que no hace falta un `if got_lock:` en cada paso (el
    lock recién adquirido, sin ambigüedad, es justo lo que ese `finally`
    protege de punta a punta — ver más abajo). No confundir con la Tarea 10:
    cuando el lock está tomado por OTRO proceso, `iniciar_generacion` ya
    cobró antes de lanzar este hilo, pero es una carga legítima —alguien más
    lo está generando (u otro intento sobre la MISMA `Interpretation`, ver
    `test_lock_tomado_no_genera_ni_cobra_de_nuevo`) y esa llamada, no ésta,
    es responsable de terminarlo o de devolver si falla.

    HALLAZGO 3 de code review: la guarda de la devolución (ver `finally`)
    NO usa `sibling is None`, aunque `sibling` sigue existiendo para decidir
    el camino de traducir-vs-generar (arriba). `sibling` es una foto de la
    base tomada ACÁ, en el hilo de fondo — un instante distinto del que usó
    `iniciar_generacion` para decidir si cobraba. Si `iniciar_generacion`
    encontró un sibling completo (no cobró) y ese sibling desaparece antes
    de que corra esta función (p. ej. se borra esa interpretación), `sibling`
    recién calculado da `None` aunque acá nunca se cobró nada — devolver en
    ese caso acredita un crédito que nunca se debitó. La guarda correcta no
    es "¿existe un sibling ahora?" sino "¿esta carta y este tier tienen un
    `Movimiento` de consumo?" (Task 11: antes era "¿esta `Interpretation`
    tiene una `CreditTransaction` de consumo?" — `canje.canjear` ya no deja
    un rastro por fila, deja uno por (chart, tier); ver la nota de `consumo`
    más abajo).

    Task 10 / RF21: la guarda de devolución YA NO es "no quedó ninguna
    sección" — con el informe pago (US$ 29), un intento que dejó tres
    secciones escritas y después falla no puede tratarse como "sin
    trabajo perdido" solo porque hay texto en la base; ese texto no se
    muestra (`completa=False` sigue dando 404) y el usuario pagó el
    informe entero, no tres octavos. La política nueva es contar intentos
    (`interpretacion.intentos`, incrementado en cada llamada que sí toma el
    lock) y, agotados `INTENTOS_MAXIMOS` sin llegar a `completa=True`,
    rendirse: devolver el crédito, borrar la interpretación (y sus
    secciones, `on_delete=CASCADE`) y avisar por `api.notificaciones` —
    nunca dejar mostrable un informe a medias."""
    if interpretacion.completa:
        return

    lock_key = _lock_key(chart, interpretacion.tier)
    token = uuid.uuid4().hex
    got_lock = cache.add(lock_key, token, timeout=LOCK_TTL)

    from api import informe_service  # import diferido: ver nota al tope del módulo

    if not got_lock:
        logger.info(
            "ya hay una generación en curso para la carta %s; se ignora este pedido",
            chart.pk,
        )
        return

    lock_perdido = False
    # Hallazgo de la wave de fix final, post-review: TODO lo que corre desde
    # acá hasta soltar el lock vive en ESTE `try/finally` único —no en un
    # `finally` con múltiples pasos sueltos, aunque sea "sólo una consulta
    # más"—. La versión anterior calculaba `sibling`, `consumo` y
    # `completo_ahora` como sentencias sueltas (una antes del `try`, dos
    # dentro del `finally` pero antes de su propio `try` interno): si
    # CUALQUIERA de esas consultas reventaba —no hace falta que sea la
    # generación en sí—, la excepción escapaba ANTES de llegar al
    # `soltar_lock` de más abajo y el lock quedaba colgado hasta el TTL
    # (600 s). Se reprodujo de verdad: un test preexistente
    # (`test_delete_charts_preserva_ledger`) dispara esta función en un hilo
    # de fondo que sigue vivo cuando el hilo principal del test ya está
    # borrando la carta; bajo SQLite (no bajo Postgres, que sí soporta
    # lectores/escritores concurrentes de verdad) eso da
    # `sqlite3.OperationalError: database table is locked` justo en la
    # consulta de `sibling`, ANTES de entrar al `try` que protegía sólo la
    # generación — el lock de la carta quedaba tomado para siempre (dentro
    # de la corrida de tests) y envenenaba cualquier test posterior que
    # reusara la misma carta y el mismo tier. Ese SQLite `OperationalError`
    # específico es un artefacto de test (un hilo de fondo sin esperar en un
    # test que no es mío), pero el bug de fondo —una consulta cualquiera
    # after `got_lock=True` puede tirar el lock a la basura— es real y
    # existía en producción también, no sólo en el test.
    try:
        sibling = _sibling_completo(chart, interpretacion.lang, interpretacion.tier)

        # Un intento más de terminar este informe, cuente como generación o
        # como traducción de un sibling: las dos pueden fallar, y las dos
        # cuentan contra `INTENTOS_MAXIMOS`.
        interpretacion.intentos += 1
        interpretacion.save(update_fields=["intentos"])
        try:
            if sibling is not None:
                # Si ya existe un informe completo de esta carta en otro
                # idioma, traduce ese informe (`informe_service.
                # traducir_informe`, Tarea 9) en vez de generar desde cero:
                # es gratis (RF8, ya lo decidió `iniciar_generacion` no
                # cobrando) y evita pagarle al modelo ocho secciones que ya
                # existen en otro idioma.
                informe_service.traducir_informe(sibling, interpretacion.lang, _build_client())
            else:
                # Fix wave final / Important: `generar_informe` devuelve
                # `False` cuando abortó de forma LIMPIA porque perdió el
                # lock (otro proceso lo tomó y sigue escribiendo esta MISMA
                # interpretación ahora mismo) — eso no es que este intento
                # haya fracasado, es que se lo cedimos a quien lo tiene. Sin
                # distinguirlo, tres abortos así agotaban
                # `INTENTOS_MAXIMOS` como si fueran tres fallos reales y
                # devolvían + borraban una fila que el otro proceso estaba
                # terminando de verdad.
                lock_perdido = not informe_service.generar_informe(interpretacion, _build_client(), token)
        except Exception:
            # Nunca deja una excepción sin loguear: si el hilo de fondo
            # muere en silencio, el informe queda colgado con el crédito ya
            # cobrado y nadie se entera hasta que el usuario se queja. Este
            # `except` sólo cubre generar/traducir (no la devolución de más
            # abajo, que si revienta necesita propagarse — ver el docstring
            # de la función) por eso vive en su propio `try` interno, no en
            # el externo que abarca hasta `soltar_lock`.
            logger.exception("la generación del informe %s falló", interpretacion.pk)

        if lock_perdido:
            # Se descuenta el intento que se cargó preventivamente arriba,
            # antes de saber cómo terminaba: un aborto por lock perdido no
            # cuenta contra `INTENTOS_MAXIMOS`.
            interpretacion.intentos = max(interpretacion.intentos - 1, 0)
            interpretacion.save(update_fields=["intentos"])

        # `consumo` (Task 11): ya no hay una `CreditTransaction` por
        # `Interpretation` — `canje.canjear` deja un `Movimiento` de
        # `chart` (no de interpretación puntual, ver docstring de
        # `canjear`), así que el dato que sobrevive es "¿esta carta y este
        # tier tienen un consumo todavía vinculado?" en vez de "¿cobré ESTA
        # fila?". `codigo` es el mismo producto del que `iniciar_generacion`
        # cobró (Task 11, `CODIGO_POR_TIER`), así que `devolver` siempre
        # acredita al derecho correcto (mismo cuidado que antes tenía
        # `ledger.devolver` sobre el lote).
        codigo = CODIGO_POR_TIER[interpretacion.tier]
        consumo = Movimiento.objects.filter(
            chart=chart, tipo="consumo", codigo_producto=codigo,
        ).exists()
        # Critical de la revisión final: `interpretacion.completa` en
        # MEMORIA no ve una traducción exitosa. `informe_service.
        # traducir_informe` resuelve su `destino` con un `get_or_create`
        # PROPIO — la MISMA fila por el `unique_together (chart, lang,
        # prompt_version, tier)`, pero OTRO objeto Python — y escribe
        # `completa=True` AHÍ, nunca sobre `interpretacion`. Sin este
        # chequeo fresco, un intento que traduce con éxito (porque mientras
        # tanto terminó un sibling en otro idioma) veía `interpretacion.
        # completa` stale en `False` y, si además agotaba los intentos,
        # devolvía el crédito y borraba un informe que se acababa de
        # entregar.
        #
        # Task 11: el chequeo es por CHART+TIER (cualquier idioma), no sólo
        # por `interpretacion.pk`. La compra es por chart+tier, no por
        # idioma (RF8): si otro idioma de esta misma carta y tier ya se
        # entregó, esta carta YA cobró lo que debía cobrar y no hay nada que
        # devolver aunque la traducción a ESTE idioma en particular siga
        # fallando — devolver ahí le sacaría a la cuenta un derecho por un
        # informe que sí se entregó, sólo en otro idioma.
        completo_ahora = Interpretation.objects.filter(
            chart=chart, prompt_version=PROMPT_VERSION, tier=interpretacion.tier, completa=True,
        ).exists()
        # Task 10 / RF21: ya no "sin secciones" sino "sin completar tras
        # agotar los intentos" — devolver antes de agotarlos regalaría el
        # reintento gratis (el crédito ya compró el trabajo hecho hasta
        # acá) y no devolver nunca dejaría cobrado un informe que jamás
        # puede terminar de generarse.
        if (
            consumo
            and not completo_ahora
            and interpretacion.intentos >= INTENTOS_MAXIMOS
        ):
            pk = interpretacion.pk
            chart_uuid = str(chart.uuid)
            tier = interpretacion.tier
            lang = interpretacion.lang
            devolver(
                account, codigo,
                external_id=f"informe:{pk}:devolucion",
                chart=chart,
                note=f"informe {pk} sin completar tras {INTENTOS_MAXIMOS} intentos",
            )
            # No se muestran las secciones sueltas de un informe que no se
            # pudo entregar (decisión del dueño del producto): se borra
            # entero, no sólo se marca. `InterpretationSection.interpretation`
            # es CASCADE, así que esto se lleva las secciones puestas.
            interpretacion.delete()
            notificaciones.notificar(
                account, "informe_no_entregado",
                {"chart": chart_uuid, "tier": tier},
                lang=lang,
            )
    finally:
        # Soltar el lock es lo ÚLTIMO que hace esta función, en el `finally`
        # MÁS EXTERNO posible sobre todo lo que corre con el lock tomado
        # (sibling, intentos, generar/traducir, devolución) — no sólo sobre
        # el tramo de devolución. Corre pase lo que pase arriba, incluida
        # una excepción sin atrapar en `devolver`/`notificar` (que
        # sigue propagándose después de este `finally`, igual que antes).
        # Sigue corriendo DESPUÉS de intentar el `delete()` (no antes):
        # soltarlo antes abriría una ventana para que otro proceso tome el
        # lock y empiece a escribir sobre una fila que esta misma llamada
        # está por borrar — la misma clase de carrera que el hallazgo
        # Critical de arriba.
        soltar_lock(chart, interpretacion.tier, token)


def generar_en_segundo_plano(chart, lang: str, account, tier: str) -> None:
    """Arranca (o reanuda) el informe de principio a fin, para el tier
    pedido: `iniciar_generacion` + `completar_generacion`.

    El nombre es el contrato de la Tarea 10 con la vista y con los tests: la
    vista NO la llama a ella (necesita el resultado de `iniciar_generacion`
    antes de responder, para poder devolver 402/503 sincrónicamente), pero
    todo lo demás —un cron, un management command, o un test que quiere
    correr el flujo entero sincrónico sobre su propia conexión— sí."""
    interpretacion = iniciar_generacion(chart, lang, account, tier)
    completar_generacion(interpretacion, chart, account)
