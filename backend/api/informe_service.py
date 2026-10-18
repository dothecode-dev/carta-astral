"""Armado del informe de ocho secciones.

Vive fuera de `views.py` porque `api/` ya es grande y la lógica va en módulos
de servicio. La propiedad que sostiene todo lo demás es que **cada sección se
guarda apenas se termina**: eso es lo que hace la generación reanudable sin
agregar una cola de trabajos, y lo que impide pagarle dos veces al modelo por
el mismo párrafo.
"""

import logging
import re
import time
import unicodedata
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from api import notificaciones
from api.firma_frases import firma
from api.interpretation_service import renovar_lock
from api.models import Interpretation, InterpretationSection, Sujeto
from interpret.generator import build_interpretation, build_seccion, translate_interpretation
from interpret.prompts import PROMPT_VERSION, SECCION_BREVE, TIER_CORTO, TIER_LARGO, Seccion, secciones_natal
from interpret.reparto import bloque as bloque_de_reparto
from interpret.reparto import parte_de
from interpret.revision_trato import revisar_personas, revisar_trato
from interpret.vinculo import build_seccion_vinculo, secciones_vinculo

logger = logging.getLogger(__name__)

# Cuánto de cada sección ya escrita viaja como contexto de la siguiente. El
# informe entero no entra en el prompt; el primer párrafo alcanza para que no
# se repitan y mantiene el input acotado.
RESUMEN_POR_SECCION = 400

# Presupuesto total de palabras del resumen gratis (RF3: "menos de 400
# palabras"). Es un tope, no un objetivo: `_tope_por_seccion` reparte
# PRESUPUESTO_GRATIS - 1 entre las secciones aplicables para garantizar la
# desigualdad estricta pase lo que pase con la división entera (con 400 y
# ocho secciones el reparto da justo 50 y el total daría exactamente 400,
# que no es "menos de 400").
PRESUPUESTO_GRATIS = 400

# Signos de puntuación que no pueden quedar pegados a una elipsis de corte.
_PUNTUACION_COLGANTE = " ,;:.!?¡¿-—"


def _datos(sujeto) -> dict:
    """El cálculo sobre el que se escribe el informe. El natal lo tiene en su
    carta; el vínculo, en sus dos copias y en `sujeto.data` (sin alias, RF22)."""
    if sujeto.producto == Sujeto.VINCULO:
        from api.vinculo_service import datos_prompt

        return datos_prompt(sujeto)
    return sujeto.natal_de.data


def _generos(sujeto) -> tuple[str, str]:
    from api.vinculo_service import generos

    return generos(sujeto)


def secciones_aplicables(sujeto, tier: str) -> list[Seccion]:
    """El catálogo del informe pedido.

    El corto es una sola sección; el largo son las ocho, menos las que dependen
    de una hora de nacimiento que no está. El tier no abre un camino de
    generación nuevo: cambia esta lista, y todo lo demás (lock, persistencia,
    reanudabilidad, estado, PDF) sigue igual.

    Sin valor por defecto a propósito: un default convertiría "me olvidé de
    pasar el tier" en "le muestro ocho secciones a quien compró una", en
    silencio. Los llamadores son `secciones_pendientes`, `resumen_gratis`
    (siempre `largo`: describe el informe completo), `generar_informe`,
    `pdf_payload` y la vista de estado."""
    if sujeto.producto == Sujeto.VINCULO:
        datos = _datos(sujeto)
        hay_hora = any(
            datos[p]["carta"].get("time_known", True) for p in ("persona_a", "persona_b")
        )
        return secciones_vinculo(datos["tipo"], hay_hora)
    if tier == TIER_CORTO:
        return [SECCION_BREVE]
    hora = _datos(sujeto).get("time_known", True)
    return secciones_natal(hora)


def secciones_pendientes(interpretacion) -> list[Seccion]:
    hechas = set(interpretacion.secciones.values_list("slug", flat=True))
    aplicables = secciones_aplicables(interpretacion.sujeto, interpretacion.tier)
    return [s for s in aplicables if s.slug not in hechas]


def resumen_previo(interpretacion) -> str:
    return "\n\n".join(
        s.texto[:RESUMEN_POR_SECCION] for s in interpretacion.secciones.all()
    )


def _tope_por_seccion(cantidad_aplicables: int) -> int:
    """Cuántas palabras del párrafo de apertura se muestran por sección.

    `SYSTEM_PROMPTS_SECCION` no le pone largo al párrafo de apertura de una
    sección (a propósito: fijarlo ahí sería una expectativa sobre el modelo,
    no una garantía). El tope vive acá, derivado del presupuesto total, para
    que ninguna combinación de secciones aplicables pueda superar
    `PRESUPUESTO_GRATIS` palabras."""
    return (PRESUPUESTO_GRATIS - 1) // cantidad_aplicables


def _primer_parrafo(texto: str) -> str:
    """El primer bloque de PROSA de una sección, salteando encabezados.

    El modelo arranca algunas secciones repitiendo el título como encabezado
    markdown, y quedarse con el primer bloque a secas se lo llevaba tal cual:
    el 01-09-2026 el teaser mostraba "## Tu firma" en crudo debajo de "Tu
    firma". Un encabezado no es el arranque de la sección —es su título, que
    el resumen ya muestra aparte en `titulo`— y el componente que lo pinta lo
    hace como texto plano, así que la almohadilla se ve.

    Se limpia acá, al leer, y no al persistir: así también quedan cubiertas
    las secciones que ya están escritas en la base. Que el modelo no ponga el
    encabezado no se puede garantizar desde el prompt (sería una expectativa
    sobre el modelo, no una garantía — mismo criterio que `_tope_por_seccion`).
    """
    for bloque in texto.split("\n\n"):
        bloque = bloque.strip()
        if bloque and not bloque.startswith("#"):
            return bloque
    return ""


def _abrir(parrafo: str, tope: int) -> tuple[str, int]:
    """Corta `parrafo` a lo sumo a `tope` palabras, en el límite de palabra.

    Si corta, lo marca con una elipsis (un texto que termina de golpe se lee
    como un error; uno que sigue con "…" se lee como "hay más, pagá para
    verlo") y nunca deja un espacio o un signo de puntuación pegado a esa
    elipsis. Si el párrafo real es más corto que el tope, se devuelve entero
    y sin agregarle nada.

    Devuelve el texto a mostrar y cuántas palabras del original se muestran
    (sin contar la elipsis) — lo que hace falta para calcular `restante`.
    """
    palabras = parrafo.split()
    if len(palabras) <= tope:
        return parrafo, len(palabras)
    mostrado = " ".join(palabras[:tope]).rstrip(_PUNTUACION_COLGANTE)
    return mostrado + "…", tope


def resumen_gratis(interpretacion) -> list[dict]:
    """Lo que ve quien no pagó: el índice completo y el arranque de cada
    sección (RF3).

    No es la primera sección recortada. La primera sección es Sol, Luna y
    Ascendente —justo lo que más le importa a la gente—, y regalarla entera
    hace que quien la lee ya no tenga por qué pagar.

    El índice sale de `secciones_aplicables(sujeto, "largo")` —el catálogo,
    filtrado por si hay hora de nacimiento—, no de
    `interpretacion.secciones.all()`. Siempre `"largo"`, no
    `interpretacion.tier`: este resumen describe el informe completo que se
    compra, no el tier de la interpretación (gratis, todavía sin comprar) que
    lo está generando. La generación corre fuera del request y es reanudable
    (RF10): este resumen tiene que poder mostrarse con el informe a medio
    generar, y tiene que nombrar las ocho secciones (o las siete que aplican
    sin hora) aunque todavía falten por escribirse. Las que no están
    generadas todavía aparecen con su título y sin párrafo.

    El párrafo de apertura de cada sección generada se recorta a
    `_tope_por_seccion(...)` palabras: el modelo escribe secciones de 700 a
    1000 palabras y no tiene ningún tope sobre el largo del párrafo de
    apertura, así que sin este recorte el resumen entero podía superar
    ampliamente las 400 palabras que promete RF3.
    """
    aplicables = secciones_aplicables(interpretacion.sujeto, TIER_LARGO)
    tope = _tope_por_seccion(len(aplicables))
    generadas = {s.slug: s for s in interpretacion.secciones.all()}
    salida = []
    for seccion in aplicables:
        existente = generadas.get(seccion.slug)
        if existente is None:
            parrafo, restante = "", seccion.palabras
        else:
            total_palabras = len(existente.texto.split())
            parrafo, mostradas = _abrir(_primer_parrafo(existente.texto), tope)
            restante = total_palabras - mostradas
        salida.append({
            "slug": seccion.slug,
            "titulo": seccion.titulo[interpretacion.lang],
            "parrafo": parrafo,
            "restante": restante,
        })
    return salida


def indice_informe(sujeto, lang: str) -> list[dict]:
    """El índice del informe completo (RF3): los títulos de las ocho
    secciones (o las siete que aplican sin hora de nacimiento) y, si ya hay
    algo generado, el arranque de cada una. Es lo que ve quien todavía no
    compró, para decidir si compra.

    Si ya existe una `Interpretation` tier=largo vigente (mismo
    `PROMPT_VERSION`) para este `(sujeto, lang)`, delega en `resumen_gratis`,
    que arma el índice con el arranque recortado de cada sección ya escrita
    —el informe puede estar a medio generar (RF10) y el índice tiene que
    poder mostrarse igual. Si no existe —el caso más común: nadie generó
    (ni pagó) este informe todavía— arma el mismo índice a mano desde el
    catálogo, con `parrafo` vacío y `restante` igual al objetivo de palabras
    de cada sección: sirve igual como vidriera de lo que se compra.
    """
    interpretacion = sujeto.interpretations.filter(
        lang=lang, prompt_version=PROMPT_VERSION, tier=TIER_LARGO,
    ).first()
    if interpretacion is not None:
        return resumen_gratis(interpretacion)
    return [
        {"slug": seccion.slug, "titulo": seccion.titulo[lang], "parrafo": "", "restante": seccion.palabras}
        for seccion in secciones_aplicables(sujeto, TIER_LARGO)
    ]


def _normalizar(texto: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return "".join(c for c in sin_acentos.lower() if c.isalnum())


def _sin_titulo(texto: str, titulo: str) -> str:
    """Quita la primera línea SÓLO si repite el título de la sección: como
    encabezado markdown, en negrita o en texto plano.

    El título lo pone el catálogo (la web lo pinta como `h2` con ancla para el
    índice). Un subtítulo propio del modelo, o una primera línea que sólo
    empieza como el título, es contenido y se queda: la comparación es de
    igualdad. Se limpia al leer, no al guardar: cubre también los informes ya
    escritos."""
    cabeza, _, resto = texto.lstrip().partition("\n")
    if _normalizar(cabeza) == _normalizar(titulo):
        return resto.lstrip("\n")
    return texto


def secciones_escritas(interpretacion) -> list[dict]:
    """Las secciones que ya están, con su texto entero, para leerlas mientras
    se escriben las demás. Son las mismas filas que después forman `text`."""
    titulos = {
        s.slug: s.titulo[interpretacion.lang]
        for s in secciones_aplicables(interpretacion.sujeto, interpretacion.tier)
    }
    return [
        {
            "slug": s.slug,
            "titulo": titulos.get(s.slug, s.slug),
            "texto": _sin_titulo(s.texto, titulos.get(s.slug, s.slug)),
        }
        for s in interpretacion.secciones.all()
    ]


def escribir_breve(chart_data: dict, lang: str, trato: str, client) -> str:
    """La lectura breve: un informe entero corto, revisado por el juez del
    trato. La usan la breve con cuenta y la anónima (`api.lectura_anonima`):
    las dos tienen que dar el mismo texto (spec 2026-10-08, RF2)."""
    texto = build_interpretation(chart_data, lang, PROMPT_VERSION, client, trato=trato)
    return revisar_trato(texto, trato, lang, client)


def avisar_informe_listo(interpretacion: Interpretation) -> None:
    """Manda «tu informe está listo» una sola vez por informe (spec 2026-10-08,
    RF23). El UPDATE condicional decide quién avisa si el hilo y el cron
    terminan a la vez; `notificar` ya traga y loguea los fallos de Resend.
    La entrega es at-most-once a propósito: `avisada_at` se marca antes de
    mandar, así que un crash o un fallo de Resend no se reintenta."""
    if interpretacion.tier != TIER_LARGO or interpretacion.account_id is None:
        return
    marcadas = Interpretation.objects.filter(
        pk=interpretacion.pk, avisada_at__isnull=True,
    ).update(avisada_at=timezone.now())
    if marcadas != 1:
        return
    # El informe vive en la página de la carta (web/app/[locale]/carta/[id],
    # `id` = uuid) o del vínculo, no en la cuenta: el mail lleva directo a leerlo.
    sujeto = interpretacion.sujeto
    if sujeto.producto == Sujeto.VINCULO:
        contexto = {"vinculo": str(sujeto.uuid), "ruta": f"/vinculo/{sujeto.uuid}"}
    else:
        uuid = str(sujeto.natal_de.uuid)
        contexto = {"chart": uuid, "ruta": f"/carta/{uuid}"}
    contexto.update(_contexto_de_la_carta(interpretacion))
    notificaciones.notificar(
        interpretacion.account, "informe_listo", contexto, lang=interpretacion.lang,
    )


# Cuánto del informe viaja en el mail: el arranque, no la sección. Unas 45
# palabras son tres o cuatro renglones; leerlo entero es entrar a la página.
_ARRANQUE_PALABRAS = 45


# Énfasis y código en línea del markdown: asteriscos, comillas invertidas y
# guiones bajos que abren o cierran una palabra («_tensión_»); el de
# `snake_case` no se toca.
_MARCAS_MARKDOWN = re.compile(r"[*`]|(?<!\w)_|_(?!\w)")


def _sin_markdown(texto: str) -> str:
    return _MARCAS_MARKDOWN.sub("", texto)


def _contexto_de_la_carta(interpretacion: Interpretation) -> dict:
    """Lo que el mail de «informe listo» muestra de la carta: el nombre,
    Sol/Luna/Ascendente y el arranque del informe (decisión del 10-10-2026).
    La fecha y el lugar de nacimiento NO viajan: menos datos personales por
    mail, y quien lo recibe ya los sabe. Es adorno sobre un aviso que ya está decidido: si algo acá
    falla se loguea con traceback y el mail sale igual, sin adornos."""
    try:
        sujeto = interpretacion.sujeto
        primera = secciones_escritas(interpretacion)
        arranque, _ = _abrir(
            _sin_markdown(_primer_parrafo(primera[0]["texto"])), _ARRANQUE_PALABRAS,
        ) if primera else ("", 0)
        if sujeto.producto == Sujeto.VINCULO:
            from api.vinculo_api import sustituir_alias
            from api.vinculo_service import alias

            alias_ = alias(sujeto)
            return {
                "alias": list(alias_),
                "arranque": sustituir_alias(arranque, alias_, interpretacion.lang) if arranque else "",
            }
        carta = sujeto.natal_de
        nacimiento = carta.birth_data
        return {
            "nombre": nacimiento.name or "",
            "signos": [[f["cuerpo"], f["signo"]] for f in firma(carta.data)],
            "arranque": arranque,
        }
    except Exception:
        logger.exception("no se pudo armar la carta del mail de informe listo (%s)", interpretacion.pk)
        return {}


# Las secciones que hablan de «todo lo anterior»: no pueden escribirse a la vez
# que las demás porque su pedido es el resumen de lo ya escrito. Hoy es la
# síntesis, en el natal y en el vínculo. Se escriben en una segunda ola.
_DEPENDEN_DE_LO_ESCRITO = frozenset({"sintesis"})


def _en_paralelo(
    items: Sequence, trabajo: Callable, paralelismo: int,
) -> Iterator[tuple]:
    """Corre `trabajo(item)` en hilos y entrega `(item, (resultado, segundos),
    error)` a medida que terminan.

    El trabajo tiene que ser SÓLO llamadas al modelo: devuelve texto y no toca
    la base. Quien consume este iterador es el único que persiste, así que
    ningún hilo abre una conexión que nadie cierra.

    Hay a lo sumo `paralelismo` items en vuelo, y el siguiente se lanza recién
    cuando quien consume terminó con el anterior. Por eso un corte es
    determinista: si el coordinador deja de iterar (perdió el lock) o hubo un
    error, no se arranca nada nuevo —con `paralelismo=1` es exactamente el
    comportamiento en serie de antes— y lo que ya estaba en vuelo se entrega
    (ya se pagó) o, si se cortó la iteración, termina solo y se descarta.
    """
    if not items:
        return

    def _medido(item):
        t0 = time.monotonic()
        return trabajo(item), time.monotonic() - t0

    por_lanzar = iter(items)
    en_vuelo: dict = {}
    fallo = False
    maximo = max(1, min(paralelismo, len(items)))
    pool = ThreadPoolExecutor(max_workers=maximo, thread_name_prefix="informe")
    try:
        while True:
            while not fallo and len(en_vuelo) < maximo:
                item = next(por_lanzar, None)
                if item is None:
                    break
                en_vuelo[pool.submit(_medido, item)] = item
            if not en_vuelo:
                return
            terminados, _ = wait(en_vuelo, return_when=FIRST_COMPLETED)
            for futuro in terminados:
                item = en_vuelo.pop(futuro)
                try:
                    resultado, error = futuro.result(), None
                except Exception as exc:  # se entrega al coordinador, que decide
                    resultado, error = None, exc
                    fallo = True
                yield item, resultado, error
    finally:
        pool.shutdown(wait=False, cancel_futures=True)


@dataclass(frozen=True)
class _Contexto:
    """Todo lo que una sección necesita para escribirse, ya leído de la base:
    los hilos de trabajo no tocan el ORM."""

    producto: str
    datos: dict
    lang: str
    trato: str
    slugs: list[str]
    titulos: dict[str, str]
    aplicables: tuple[Seccion, ...]
    generos: tuple[str, str] | None


def _escribir_seccion(seccion: Seccion, ctx: _Contexto, previo: str, client) -> str:
    """El texto de una sección, con su revisión de género. Sólo llamadas al
    modelo (ver `_en_paralelo`)."""
    if ctx.producto == Sujeto.VINCULO:
        # Sin reparto de aspectos ni juez del lector: el vínculo va en tercera
        # persona. Sí un mapa de las demás secciones, para que no se pisen, y
        # el juez del género de cada persona (medido en staging el 10-10:
        # «se percibe a sí mismo» con las dos en neutro).
        otras = tuple(o for o in ctx.aplicables if o.slug != seccion.slug)
        texto = build_seccion_vinculo(ctx.datos, seccion, ctx.lang, previo, client, otras)
        return revisar_personas(texto, ctx.generos, ctx.lang, client)
    if seccion.slug == SECCION_BREVE.slug:
        # La breve es un informe entero corto, no un recorte del largo:
        # SYSTEM_PROMPTS_SECCION le diría al modelo que está escribiendo
        # una parte de algo mayor y produciría un texto que remite a
        # secciones que nadie va a leer (ver interpret/prompts.py).
        # `escribir_breve` ya la pasa por el juez del trato.
        return escribir_breve(ctx.datos, ctx.lang, ctx.trato, client)
    texto = build_seccion(
        ctx.datos, seccion, ctx.lang, previo, client,
        reparto=bloque_de_reparto(
            parte_de(ctx.datos, seccion.slug, ctx.slugs), ctx.lang, ctx.titulos,
        ),
        trato=ctx.trato,
    )
    # El modelo no cumple el trato al 100% (medido en staging el 08-10:
    # «vos misma» en un informe neutro). Un juez lo revisa y, si hace
    # falta, se repara; ante cualquier duda devuelve el texto tal cual.
    return revisar_trato(texto, ctx.trato, ctx.lang, client)


def generar_informe(interpretacion, client, token: str) -> bool:
    """Genera las secciones que falten. Reanudable: llamarla dos veces sobre un
    informe a medio hacer completa el resto sin repetir lo ya escrito.

    Devuelve `True` si terminó de intentar (con el informe completo o no —
    eso lo dice `interpretacion.completa`, no el valor de retorno) y `False`
    únicamente cuando abortó de forma limpia porque perdió el lock a mitad
    de camino (ver más abajo). Fix wave final / Important: `completar_generacion`
    necesita distinguir ESE aborto de un fallo real para no contarlo como un
    intento fallido — perder el lock no es que este intento haya fracasado,
    es que otro proceso vivo se quedó con el trabajo.

    `token` es el mismo valor que `interpretation_service` guardó al tomar el
    lock de esta carta en `completar_generacion`. Después de persistir CADA sección
    se llama a `renovar_lock(sujeto, tier, token)`: un informe son ocho llamadas
    secuenciales de hasta 1000 palabras, unos 6 minutos contra un
    `LOCK_TTL = 600`, así que sin renovar el lock la generación sobrevive a su
    propio candado. Si `renovar_lock` devuelve `False` el lock YA NO ES
    NUESTRO —otro proceso lo tomó porque el nuestro expiró— y esa función
    aborta de forma limpia: no sigue pidiendo secciones, no marca `completa`,
    no toca el ledger. Seguir generando en ese momento significaría dos
    procesos escribiendo las mismas secciones.

    HALLAZGO 4 de code review: ese abort sólo importa si TODAVÍA queda
    trabajo pendiente. `renovar_lock` se llama después de CADA sección,
    incluida la última — y si falla justo ahí, ya no hay ninguna sección más
    que pedir: el informe está entero. Abortar en ese punto (como hacía la
    versión vieja) dejaba un informe completo marcado `completa=False` para
    siempre —404 en el GET, ausente del PDF— por perder un lock que ya no
    hacía falta. Por eso el resultado de `renovar_lock` sólo aborta cuando
    `secciones_pendientes` diga que falta al menos una más.

    Desde el 10-10-2026 las secciones se escriben a la vez (spec
    `2026-10-10-spec-informe-rapido`): un intento ya no es «una sección tras
    otra». Si una falla, las que estaban en vuelo igual se persisten y el
    intento cuenta como uno; el reintento retoma sólo las que faltan. La
    síntesis, que habla de «todo lo anterior», va sola en una segunda ola.
    El lock se renueva tras cada sección persistida, con el mismo contrato.

    Contrato de crédito para quien llama (hoy nadie; la Tarea 10 es quien
    decide si cobra y si devuelve, no esta función):

    - Esta función NUNCA llama a `ledger.devolver`. No le corresponde: genera
      y persiste, no decide sobre plata. Ni siquiera cuando pierde el lock —
      perder el lock no es que el informe se haya arruinado, es que otro
      proceso lo sigue y probablemente lo termine.
    - `iniciar_generacion` cobra un crédito la primera vez que la
      `Interpretation` de esta carta se crea, no por cada intento: un segundo
      pedido sobre una `Interpretation` que ya existe NO vuelve a cobrar,
      sólo reanuda. Task 10 / RF21: mientras queden intentos
      (`interpretacion.intentos < INTENTOS_MAXIMOS` en
      `interpretation_service.completar_generacion`), un reintento sobre una
      `Interpretation` con secciones ya persistidas la termina gratis —
      devolver ahí sería regalar el informe completo. Sólo agotados los
      intentos SIN llegar a `completa=True` se devuelve el crédito y se
      borra la `Interpretation` entera (secciones incluidas): con el
      informe pago (US$ 29) ya no alcanza con "algo se generó" para no
      devolver — o se entrega completo, o se devuelve, y las secciones
      sueltas de un intento fallido nunca se muestran.
    - Si de todas formas se devuelve el crédito, hacerlo con
      `external_id=f"informe:{interpretacion.pk}:devolucion"` — estable, por
      informe y no por intento, para que dos llamadas que lleguen a devolver
      la MISMA `Interpretation` no dupliquen el reembolso de un solo débito.
      Esta garantía se sostiene en la base de datos (la `UniqueConstraint`
      parcial de `CreditTransaction.external_id`), no en la disciplina de
      quien llama.
    """
    aplicables = secciones_aplicables(interpretacion.sujeto, interpretacion.tier)
    orden_por_slug = {seccion.slug: indice for indice, seccion in enumerate(aplicables)}
    ctx = _Contexto(
        producto=interpretacion.sujeto.producto,
        datos=_datos(interpretacion.sujeto),
        lang=interpretacion.lang,
        trato=interpretacion.trato,
        slugs=[seccion.slug for seccion in aplicables],
        titulos={seccion.slug: seccion.titulo[interpretacion.lang] for seccion in aplicables},
        aplicables=tuple(aplicables),
        generos=(
            _generos(interpretacion.sujeto)
            if interpretacion.sujeto.producto == Sujeto.VINCULO else None
        ),
    )

    pendientes = secciones_pendientes(interpretacion)
    # Dos olas: todo lo que no depende de lo escrito, a la vez; después la
    # síntesis, con el resumen de lo que acaba de quedar en la base.
    olas = [
        [s for s in pendientes if s.slug not in _DEPENDEN_DE_LO_ESCRITO],
        [s for s in pendientes if s.slug in _DEPENDEN_DE_LO_ESCRITO],
    ]
    paralelismo = settings.INFORME_PARALELISMO
    inicio = time.monotonic()
    persistidas, error = 0, None
    duraciones: dict[str, float] = {}
    primera_s = None
    for numero_de_ola, ola in enumerate(olas):
        if not ola:
            continue
        previo = resumen_previo(interpretacion) if numero_de_ola else ""
        for seccion, resultado, fallo in _en_paralelo(
            ola, lambda s: _escribir_seccion(s, ctx, previo, client), paralelismo,
        ):
            if fallo is not None:
                error = error or fallo
                continue
            texto, segundos = resultado
            InterpretationSection.objects.create(
                interpretation=interpretacion,
                slug=seccion.slug,
                orden=orden_por_slug[seccion.slug],
                texto=texto,
            )
            persistidas += 1
            duraciones[seccion.slug] = segundos
            if seccion.slug == pendientes[0].slug:
                primera_s = time.monotonic() - inicio
            lock_renovado = renovar_lock(interpretacion.sujeto, interpretacion.tier, token)
            # El lock se renueva siempre (arriba), pero sólo importa su
            # resultado cuando falta al menos otra sección (HALLAZGO 4): perder
            # el lock justo tras la última no tiene nada más que proteger.
            if not lock_renovado and persistidas < len(pendientes):
                logger.warning(
                    "se perdió el lock del informe (interpretation=%s) a mitad de "
                    "generación; otro proceso lo tomó, se aborta sin tocar el ledger",
                    interpretacion.pk,
                )
                return False
        if error is not None:
            # Lo que ya estaba en vuelo quedó persistido; el intento cuenta
            # como uno y el reintento retoma sólo lo que falta.
            raise error

    if pendientes:
        # Observabilidad (spec informe-rapido, RF11): cuánto tarda un informe y
        # qué sección manda. Sin texto del informe.
        logger.info(
            "informe generado: interpretation=%s lang=%s tier=%s secciones=%s "
            "paralelismo_max=%s total_s=%.1f primera_s=%.1f por_seccion=%s",
            interpretacion.pk, interpretacion.lang, interpretacion.tier, persistidas,
            paralelismo, time.monotonic() - inicio, primera_s or 0.0,
            ",".join(f"{slug}:{seg:.0f}" for slug, seg in duraciones.items()),
        )

    with transaction.atomic():
        interpretacion.text = "\n\n".join(
            s.texto for s in interpretacion.secciones.all()
        )
        interpretacion.completa = True
        interpretacion.save(update_fields=["text", "completa"])
    avisar_informe_listo(interpretacion)
    return True


def traducir_informe(origen: Interpretation, destino_lang: str, client, token: str) -> bool:
    """Traduce a `destino_lang` un informe ya generado (o a medio generar),
    sección por sección. Gratis para quien lo pide (RF8): el crédito se cobró
    una vez, en el primer idioma; esta función no debita ni devuelve nada del
    ledger, ni siquiera si se corta a mitad.

    `translate_interpretation` traduce de a un texto por llamada y las ocho
    secciones juntas (hasta 6.400 palabras) no entran en una sola: por eso
    acá se traduce sección por sección, igual que `generar_informe` genera
    sección por sección.

    Reanudable con el mismo mecanismo que `generar_informe`: cada sección
    traducida se persiste apenas se termina, así que si una llamada se corta
    a mitad (`translate_interpretation` puede lanzar `InterpretationError` u
    otra excepción del cliente), las secciones ya traducidas quedan y una
    segunda llamada retoma sólo las que faltan — no le vuelve a pagar al
    modelo por lo ya traducido. El chequeo de `hechas` es lo que evita el
    trabajo repetido en el caso normal (dos llamadas secuenciales); el
    `unique_together` de `InterpretationSection` es la red de seguridad para
    la carrera real entre dos llamadas concurrentes, y el `except
    IntegrityError` de abajo es lo que atrapa esa red — sin él, la fila que
    el `unique_together` bloqueó se cae como una excepción sin atrapar
    (un 500), no como un descarte silencioso.

    `destino.completa` copia `origen.completa` en lugar de fijarse siempre en
    `True`: si el origen todavía está a medio generar, la traducción de lo
    que hay hasta ahora tiene que quedar igual de incompleta, no mentir que
    terminó.

    El `get_or_create` de `destino` no necesita ese mismo `except`: el
    `get_or_create` de Django ya envuelve su `create()` en un `atomic()`
    propio y, si choca contra el `unique_together` de `Interpretation`
    (`sujeto`, `lang`, `prompt_version`, `tier`), vuelve a hacer el `get()`
    con esos mismos campos antes de relanzar — la carrera ahí ya está
    resuelta por el ORM, no hace falta repetirlo a mano.

    `tier=origen.tier` en el filtro (fix round 1, Important 2) no es
    opcional: sin él, con dos productos sobre la misma carta, el filtro
    (sujeto, lang, prompt_version) puede matchear la `Interpretation` del
    OTRO tier en ese idioma si ya existe —no una excepción, algo peor— y
    esta función le escribiría las secciones traducidas del `origen` encima
    de esa fila ajena, corrompiendo el informe pagado con el contenido de la
    lectura breve (o viceversa).

    `token` es el del lock que tomó `completar_generacion`, y el retorno sigue
    el contrato de `generar_informe` (fix round 2): `False` sólo cuando abortó
    de forma limpia porque perdió el lock con trabajo pendiente; `True` cuando
    terminó de intentar (incluido un destino que ya estaba completo y no se
    toca).
    """
    destino, _ = Interpretation.objects.get_or_create(
        sujeto=origen.sujeto, lang=destino_lang, prompt_version=origen.prompt_version,
        tier=origen.tier,
        defaults={
            "text": "", "account": origen.account,
            "trato": origen.trato, "traducido_de": origen,
        },
    )
    # Fix round 2: un destino que en la base ya está completo se entregó y no
    # se toca, sea o no traducción de este origen. Sin esto, quien llegara con
    # una foto vieja (el cron, con su lista armada antes de que otro hilo lo
    # terminara) descartaba las secciones de un informe ya entregado, y si la
    # re-traducción fallaba a mitad quedaba `completa=True` e incompleto.
    if destino.completa:
        return True
    # La traducción es del informe de origen y habla igual que él (RF5). El
    # destino puede existir ya: lo crea `iniciar_generacion` (con el trato
    # ACTUAL de la carta) y quizá ya tiene secciones escritas de cero por un
    # intento que falló. Regla: si `traducido_de` no es este origen, esas
    # secciones NO son traducción de él —contenido y trato propios— y se
    # descartan para traducir todo; si lo es, es un reintento y se completa lo
    # que falta. Todo en una transacción, bajo el lock de la carta que ya
    # tiene `completar_generacion`.
    if destino.traducido_de_id != origen.pk:
        with transaction.atomic():
            destino.secciones.all().delete()
            destino.traducido_de = origen
            destino.trato = origen.trato
            destino.save(update_fields=["traducido_de", "trato"])
    hechas = set(destino.secciones.values_list("slug", flat=True))
    pendientes = [s for s in origen.secciones.all() if s.slug not in hechas]
    es_natal = origen.sujeto.producto == Sujeto.NATAL
    generos = None if es_natal else _generos(origen.sujeto)
    trato_origen, trato_destino = origen.trato, destino.trato

    # Datos planos para los hilos: un objeto del ORM con un campo diferido
    # abriría una conexión a la base desde un hilo de trabajo.
    a_traducir = [(s.slug, s.orden, s.texto) for s in pendientes]

    def _traducir(pieza: tuple[str, int, str]) -> str:
        """Sólo llamadas al modelo (ver `_en_paralelo`). La traducción también
        puede escapar el género: se revisa con el idioma del destino. El natal,
        con el trato del lector (ya alineado arriba); el vínculo, en tercera
        persona, con el de cada persona."""
        original = pieza[2]
        if es_natal:
            texto = translate_interpretation(original, destino_lang, client, trato=trato_origen)
            return revisar_trato(texto, trato_destino, destino_lang, client)
        texto = translate_interpretation(
            original, destino_lang, client, trato=None, generos=generos,
        )
        return revisar_personas(texto, generos, destino_lang, client)

    persistidas, error = 0, None
    for (slug, orden, _), resultado, fallo in _en_paralelo(
        a_traducir, _traducir, settings.INFORME_PARALELISMO,
    ):
        if fallo is not None:
            error = error or fallo
            continue
        texto, _ = resultado
        try:
            with transaction.atomic():
                InterpretationSection.objects.create(
                    interpretation=destino, slug=slug, orden=orden, texto=texto,
                )
        except IntegrityError:
            # Carrera: otra llamada concurrente ya tradujo y persistió esta
            # misma sección primero (mismo patrón que `canje._movimiento_
            # idempotente`, que también distingue el duplicado real). Sólo es
            # "ya hecha" si la fila realmente está — cualquier otro
            # IntegrityError no es esta carrera y se relanza.
            if not destino.secciones.filter(slug=slug).exists():
                raise
            logger.info(
                "traducción concurrente de la sección %s (interpretation=%s, lang=%s) "
                "ya la había persistido otra llamada; se descarta la traducción repetida",
                slug, destino.pk, destino_lang,
            )
        persistidas += 1
        # Fix round 2: mismo patrón que `generar_informe` — las traducciones
        # pueden superar `LOCK_TTL`, así que el lock se renueva tras cada
        # sección y, si se perdió con trabajo pendiente, se aborta sin marcar
        # nada: otro proceso lo tiene y va a terminar este informe.
        lock_renovado = renovar_lock(origen.sujeto, origen.tier, token)
        if not lock_renovado and persistidas < len(pendientes):
            logger.warning(
                "se perdió el lock de la traducción (interpretation=%s, lang=%s) a "
                "mitad; otro proceso lo tomó, se aborta",
                destino.pk, destino_lang,
            )
            return False
    if error is not None:
        raise error

    with transaction.atomic():
        destino.text = "\n\n".join(s.texto for s in destino.secciones.all())
        destino.completa = origen.completa
        destino.save(update_fields=["text", "completa"])
    return True
