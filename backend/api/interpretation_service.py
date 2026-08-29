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

from api import ledger
from api.exceptions import CapReached, GenerationInProgress, QuotaExceeded
from api.models import CreditTransaction, Interpretation
from interpret.exceptions import InterpretationError
from interpret.prompts import PROMPT_VERSION

# Import diferido (no al tope del módulo): `informe_service` importa
# `renovar_lock` DESDE acá, así que un `import` a nivel de módulo en ambas
# direcciones sería circular. `generar_en_segundo_plano` lo importa recién al
# llamarse.

logger = logging.getLogger(__name__)

# Ocho secciones a ~30-45 s cada una. El valor viejo (30 s) soltaba el candado
# mientras el informe se seguía escribiendo, y dos pestañas generaban el mismo
# informe dos veces cobrando dos créditos.
LOCK_TTL = 600

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


def _lock_key(chart) -> str:
    return f"interp:lock:{chart.id}:{PROMPT_VERSION}"


def renovar_lock(chart, token: str) -> bool:
    """Repone el TTL del lock de esta carta mientras hay progreso real.

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
    key = _lock_key(chart)
    if cache.get(key) != token:
        return False
    return bool(cache.touch(key, LOCK_TTL))


def soltar_lock(chart, token: str) -> None:
    """Libera el lock sólo si sigue siendo el propio.

    Sin este chequeo, un proceso cuyo lock ya expiró y fue tomado por otro
    borraría el lock ajeno al terminar (o fallar) tarde. Mismo principio que
    `renovar_lock`: nunca tocar una clave cuyo token no es el nuestro.
    """
    key = _lock_key(chart)
    if cache.get(key) == token:
        cache.delete(key)


def _sibling_completo(chart, lang: str) -> Interpretation | None:
    """Informe COMPLETO de esta misma carta en otro idioma, si existe.

    Es el mismo criterio del flujo viejo de interpretación (RF8: un crédito
    por carta, no por idioma) adaptado al flujo de la Tarea 10: acá `completa`
    hace falta porque `iniciar_generacion` deja una fila vacía
    (`completa=False`) apenas arranca, y esa fila en curso no sirve como
    fuente de traducción ni cuenta como "ya pagado" — todavía no hay texto
    que traducir. `iniciar_generacion` la usa para decidir si cobra;
    `completar_generacion` la vuelve a evaluar para decidir si traduce en vez
    de generar. Recalcularla en vez de pasarla entre ambas evita acoplar sus
    firmas al resultado de la otra, a costa de una consulta extra barata."""
    return (
        Interpretation.objects.filter(chart=chart, prompt_version=PROMPT_VERSION, completa=True)
        .exclude(lang=lang)
        .first()
    )


def _sibling_en_curso(chart, lang: str) -> Interpretation | None:
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
    que antes: antes bloqueaba para SIEMPRE."""
    if cache.get(_lock_key(chart)) is None:
        return None
    return (
        Interpretation.objects.filter(chart=chart, prompt_version=PROMPT_VERSION, completa=False)
        .exclude(lang=lang)
        .first()
    )


def interpretation_langs(chart) -> list[str]:
    """Idiomas en los que esta carta ya tiene lectura completa (prompt
    actual). `completa=True` es la condición: desde la Tarea 10,
    `iniciar_generacion` crea la fila de entrada (vacía) apenas arranca el
    hilo de fondo, antes de escribir ninguna sección. Una fila así no es un
    idioma disponible, es un trabajo en curso — listarla igual es lo que
    hacía que la web pidiera un texto que todavía no existe."""
    return list(
        Interpretation.objects.filter(
            chart=chart, prompt_version=PROMPT_VERSION, completa=True,
        )
        .values_list("lang", flat=True)
    )


def content_key(chart_data: dict, lang: str, prompt_version: str) -> str:
    """Hash canónico del input del LLM. Dos cartas con el mismo JSON astrológico
    (mismo instante UTC, lugar, house system, engine) comparten lectura."""
    canonical = json.dumps(chart_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{prompt_version}:{lang}:{canonical}".encode()).hexdigest()


def iniciar_generacion(chart, lang: str, account) -> Interpretation:
    """Crea (o recupera) la `Interpretation` de un informe y cobra si
    corresponde. Corre siempre en el hilo del request —nunca en el hilo de
    fondo—: es lo que le permite a la vista responder 402/503 sincrónicamente
    en vez de aceptar un 202 que después nunca va a completarse.

    Usa `get_or_create` (no un lock) para la creación: Django envuelve su
    `create()` en `atomic()` y reconsulta ante un choque de
    `unique_together`, así que sólo UNA llamada concurrente gana `created`
    (mismo mecanismo que ya validó la Tarea 9 para `traducir_informe`). Sólo
    esa llamada cobra; la que pierde la carrera devuelve la fila existente
    sin tocar el ledger. El lock de `_lock_key` es para otra cosa —serializar
    la GENERACIÓN de secciones sobre una misma carta— y lo toma quien sigue
    con `completar_generacion`, no esta función.

    El cap diario cuenta INFORMES, no llamadas al modelo: se incrementa acá,
    una vez por `Interpretation` nueva pagada con crédito gratis, y no en
    `informe_service.generar_informe` (que hace ocho llamadas por informe).
    Con el cap actual (40) eso da ~40 informes/día × US$0.45 ≈ US$18/día; si
    contara las ocho llamadas el mismo cap alcanzaría para 5 informes por día
    y el producto se apagaría a media mañana.

    Lanza `QuotaExceeded` o `CapReached` si corresponde, y en ese caso borra
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
    que devolver porque nunca se llega a tocar el ledger."""
    interpretacion, creada = Interpretation.objects.get_or_create(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION,
        defaults={"text": "", "account": account},
    )
    if not creada:
        return interpretacion

    if _sibling_completo(chart, lang) is not None:
        return interpretacion

    if _sibling_en_curso(chart, lang) is not None:
        interpretacion.delete()
        raise GenerationInProgress(
            "hay una generación en curso para esta carta en otro idioma, "
            "reintentá en unos segundos"
        )

    will_be_free = account.free_balance > 0
    cap_key = f"interp:cap:{timezone.now().date().isoformat()}"
    if will_be_free and cache.get(cap_key, 0) >= settings.INTERPRETATION_DAILY_CAP:
        interpretacion.delete()
        logger.warning(
            "interpretation daily cap reached (cap=%s)", settings.INTERPRETATION_DAILY_CAP
        )
        raise CapReached()

    try:
        _, lot = ledger.charge(account, lambda: interpretacion)
    except QuotaExceeded:
        interpretacion.delete()
        raise

    if lot == "free":
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

    El chequeo del lock vive DENTRO del `try/finally` (no antes, con un
    `return` temprano) a propósito: la revisión de seguridad encontró que un
    `return` antes de entrar al bloque protegido salteaba el `finally` que
    devuelve el crédito, y ese es justo el tipo de bug que un refactor futuro
    podría reintroducir si el chequeo volviera a vivir afuera. Con
    `got_lock=False` el `finally` sigue corriendo igual, pero no hace nada —
    esta llamada no tocó el ledger, así que no hay nada que devolver — y
    `soltar_lock` no aplica (nunca se tomó el lock). No confundir con la
    Tarea 10: cuando el lock está tomado por OTRO proceso, `iniciar_generacion`
    ya cobró antes de lanzar este hilo, pero es una carga legítima —alguien
    más lo está generando (u otro intento sobre la MISMA `Interpretation`,
    ver `test_lock_tomado_no_genera_ni_cobra_de_nuevo`) y esa llamada, no
    ésta, es responsable de terminarlo o de devolver si falla.

    HALLAZGO 3 de code review: la guarda de la devolución (ver `finally`)
    NO usa `sibling is None`, aunque `sibling` sigue existiendo para decidir
    el camino de traducir-vs-generar (arriba). `sibling` es una foto de la
    base tomada ACÁ, en el hilo de fondo — un instante distinto del que usó
    `iniciar_generacion` para decidir si cobraba. Si `iniciar_generacion`
    encontró un sibling completo (no cobró) y ese sibling desaparece antes
    de que corra esta función (p. ej. se borra esa interpretación), `sibling`
    recién calculado da `None` aunque acá nunca se cobró nada — devolver en
    ese caso acredita un crédito que nunca se debitó. La guarda correcta no
    es "¿existe un sibling ahora?" sino "¿esta `Interpretation` tiene una
    `CreditTransaction` de consumo?" — el hecho que `iniciar_generacion`
    dejó escrito en la base cuando SÍ cobró (vía `ledger.charge`), y que no
    cambia aunque cualquier otra fila de la base sí lo haga."""
    if interpretacion.completa:
        return

    lock_key = _lock_key(chart)
    token = uuid.uuid4().hex
    got_lock = cache.add(lock_key, token, timeout=LOCK_TTL)

    from api import informe_service  # import diferido: ver nota al tope del módulo

    sibling = _sibling_completo(chart, interpretacion.lang) if got_lock else None

    try:
        if not got_lock:
            logger.info(
                "ya hay una generación en curso para la carta %s; se ignora este pedido",
                chart.pk,
            )
            return
        if sibling is not None:
            informe_service.traducir_informe(sibling, interpretacion.lang, _build_client())
        else:
            informe_service.generar_informe(interpretacion, _build_client(), token)
    except Exception:
        logger.exception("la generación del informe %s falló", interpretacion.pk)
    finally:
        # `got_lock` es la guarda: sin lock propio esta llamada nunca cobró
        # ni generó nada (ver el docstring), así que no hay crédito que
        # devolver ni lock propio que soltar.
        #
        # `consumo` (no `sibling is None`, HALLAZGO 3 de code review) es el
        # dato explícito: existe si y sólo si `iniciar_generacion` llegó a
        # llamar a `ledger.charge` para ESTA `Interpretation` — el hecho de
        # si se cobró, escrito en la base por quien lo decidió, en vez de
        # re-derivado acá sobre una foto de la base que puede haber
        # cambiado. El lote se lee ANTES de borrar: `CreditTransaction.
        # interpretation` es SET_NULL, no CASCADE, pero de todas formas hace
        # falta el dato antes de que la fila deje de existir. Se devuelve al
        # MISMO lote del que se cobró (BUG de la revisión final: antes
        # `ledger.devolver` fijaba "paid" siempre).
        consumo = (
            CreditTransaction.objects.filter(
                interpretation=interpretacion, kind="consumption",
            ).first()
            if got_lock
            else None
        )
        if got_lock and consumo is not None and not interpretacion.secciones.exists():
            pk = interpretacion.pk
            lot = consumo.lot
            interpretacion.delete()
            ledger.devolver(
                account,
                external_id=f"informe:{pk}:devolucion",
                note=f"informe {pk} sin secciones generadas",
                lot=lot,
            )
        if got_lock:
            soltar_lock(chart, token)


def generar_en_segundo_plano(chart, lang: str, account) -> None:
    """Arranca (o reanuda) el informe completo de principio a fin:
    `iniciar_generacion` + `completar_generacion`.

    El nombre es el contrato de la Tarea 10 con la vista y con los tests: la
    vista NO la llama a ella (necesita el resultado de `iniciar_generacion`
    antes de responder, para poder devolver 402/503 sincrónicamente), pero
    todo lo demás —un cron, un management command, o un test que quiere
    correr el flujo entero sincrónico sobre su propia conexión— sí."""
    interpretacion = iniciar_generacion(chart, lang, account)
    completar_generacion(interpretacion, chart, account)
