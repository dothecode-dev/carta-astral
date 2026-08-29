"""Armado del informe de ocho secciones.

Vive fuera de `views.py` porque `api/` ya es grande y la lógica va en módulos
de servicio. La propiedad que sostiene todo lo demás es que **cada sección se
guarda apenas se termina**: eso es lo que hace la generación reanudable sin
agregar una cola de trabajos, y lo que impide pagarle dos veces al modelo por
el mismo párrafo.
"""

import logging

from django.db import IntegrityError, transaction

from api.interpretation_service import renovar_lock
from api.models import Interpretation, InterpretationSection
from interpret.generator import build_interpretation, build_seccion, translate_interpretation
from interpret.prompts import PROMPT_VERSION, SECCION_BREVE, SECCIONES, TIER_CORTO, TIER_LARGO, Seccion

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


def secciones_aplicables(chart, tier: str) -> list[Seccion]:
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
    if tier == TIER_CORTO:
        return [SECCION_BREVE]
    hora = chart.data.get("time_known", True)
    return [s for s in SECCIONES if hora or not s.requiere_hora]


def secciones_pendientes(interpretacion) -> list[Seccion]:
    hechas = set(interpretacion.secciones.values_list("slug", flat=True))
    aplicables = secciones_aplicables(interpretacion.chart, interpretacion.tier)
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

    El índice sale de `secciones_aplicables(chart, "largo")` —el catálogo,
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
    aplicables = secciones_aplicables(interpretacion.chart, TIER_LARGO)
    tope = _tope_por_seccion(len(aplicables))
    generadas = {s.slug: s for s in interpretacion.secciones.all()}
    salida = []
    for seccion in aplicables:
        existente = generadas.get(seccion.slug)
        if existente is None:
            parrafo, restante = "", seccion.palabras
        else:
            primer_parrafo, _, _resto = existente.texto.partition("\n\n")
            total_palabras = len(existente.texto.split())
            parrafo, mostradas = _abrir(primer_parrafo.strip(), tope)
            restante = total_palabras - mostradas
        salida.append({
            "slug": seccion.slug,
            "titulo": seccion.titulo[interpretacion.lang],
            "parrafo": parrafo,
            "restante": restante,
        })
    return salida


def generar_informe(interpretacion, client, token: str) -> None:
    """Genera las secciones que falten. Reanudable: llamarla dos veces sobre un
    informe a medio hacer completa el resto sin repetir lo ya escrito.

    `token` es el mismo valor que `interpretation_service` guardó al tomar el
    lock de esta carta en `completar_generacion`. Después de persistir CADA sección
    se llama a `renovar_lock(chart, tier, token)`: un informe son ocho llamadas
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

    Contrato de crédito para quien llama (hoy nadie; la Tarea 10 es quien
    decide si cobra y si devuelve, no esta función):

    - Esta función NUNCA llama a `ledger.devolver`. No le corresponde: genera
      y persiste, no decide sobre plata. Ni siquiera cuando pierde el lock —
      perder el lock no es que el informe se haya arruinado, es que otro
      proceso lo sigue y probablemente lo termine.
    - `iniciar_generacion` cobra un crédito la primera vez que la
      `Interpretation` de esta carta se crea, no por cada intento: un segundo
      pedido sobre una `Interpretation` que ya existe NO vuelve a cobrar,
      sólo reanuda. Por eso el crédito se devuelve *sólo si no quedó ninguna
      sección persistida* (`not interpretacion.secciones.exists()`): con una
      sección o más el trabajo ya está comprado, y un reintento lo termina
      gratis — devolver ahí sería regalar el informe completo. Cuando no
      quedó ninguna sección, además de devolver conviene borrar esa
      `Interpretation` vacía, para que el estado quede como si el pedido
      nunca hubiera existido.
    - Si de todas formas se devuelve el crédito, hacerlo con
      `external_id=f"informe:{interpretacion.pk}:devolucion"` — estable, por
      informe y no por intento, para que dos llamadas (por ejemplo un
      `except` por sección más otro por el informe entero) no dupliquen el
      reembolso de un solo débito. La regla de "sólo con cero secciones" ya
      hace el doble reembolso improbable, pero la clave estable no es
      redundante: estas garantías se sostienen en la base de datos, no en la
      disciplina de quien llama.
    """
    aplicables = secciones_aplicables(interpretacion.chart, interpretacion.tier)
    orden_por_slug = {seccion.slug: indice for indice, seccion in enumerate(aplicables)}

    pendientes = secciones_pendientes(interpretacion)
    for indice, seccion in enumerate(pendientes):
        if seccion.slug == SECCION_BREVE.slug:
            # La breve es un informe entero corto, no un recorte del largo:
            # SYSTEM_PROMPTS_SECCION le diría al modelo que está escribiendo
            # una parte de algo mayor y produciría un texto que remite a
            # secciones que nadie va a leer (ver interpret/prompts.py).
            texto = build_interpretation(
                interpretacion.chart.data, interpretacion.lang, PROMPT_VERSION, client,
            )
        else:
            texto = build_seccion(
                interpretacion.chart.data,
                seccion,
                interpretacion.lang,
                resumen_previo(interpretacion),
                client,
            )
        InterpretationSection.objects.create(
            interpretation=interpretacion,
            slug=seccion.slug,
            orden=orden_por_slug[seccion.slug],
            texto=texto,
        )
        lock_renovado = renovar_lock(interpretacion.chart, interpretacion.tier, token)
        queda_trabajo = indice < len(pendientes) - 1
        # El lock se renueva siempre (arriba), pero sólo importa su
        # resultado cuando falta al menos otra sección (HALLAZGO 4): perder
        # el lock justo tras la última no tiene nada más que proteger.
        if not lock_renovado and queda_trabajo:
            logger.warning(
                "se perdió el lock del informe (interpretation=%s) a mitad de "
                "generación; otro proceso lo tomó, se aborta sin tocar el ledger",
                interpretacion.pk,
            )
            return

    with transaction.atomic():
        interpretacion.text = "\n\n".join(
            s.texto for s in interpretacion.secciones.all()
        )
        interpretacion.completa = True
        interpretacion.save(update_fields=["text", "completa"])


def traducir_informe(origen: Interpretation, destino_lang: str, client) -> None:
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
    (`chart`, `lang`, `prompt_version`, `tier`), vuelve a hacer el `get()`
    con esos mismos campos antes de relanzar — la carrera ahí ya está
    resuelta por el ORM, no hace falta repetirlo a mano.

    `tier=origen.tier` en el filtro (fix round 1, Important 2) no es
    opcional: sin él, con dos productos sobre la misma carta, el filtro
    (chart, lang, prompt_version) puede matchear la `Interpretation` del
    OTRO tier en ese idioma si ya existe —no una excepción, algo peor— y
    esta función le escribiría las secciones traducidas del `origen` encima
    de esa fila ajena, corrompiendo el informe pagado con el contenido de la
    lectura breve (o viceversa).
    """
    destino, _ = Interpretation.objects.get_or_create(
        chart=origen.chart, lang=destino_lang, prompt_version=origen.prompt_version,
        tier=origen.tier,
        defaults={"text": "", "account": origen.account},
    )
    hechas = set(destino.secciones.values_list("slug", flat=True))
    for seccion in origen.secciones.all():
        if seccion.slug in hechas:
            continue
        texto = translate_interpretation(seccion.texto, destino_lang, client)
        try:
            with transaction.atomic():
                InterpretationSection.objects.create(
                    interpretation=destino, slug=seccion.slug, orden=seccion.orden, texto=texto,
                )
        except IntegrityError:
            # Carrera: otra llamada concurrente ya tradujo y persistió esta
            # misma sección primero (mismo patrón que api/ledger.py). Sólo es
            # "ya hecha" si la fila realmente está — cualquier otro
            # IntegrityError no es esta carrera y se relanza.
            if not destino.secciones.filter(slug=seccion.slug).exists():
                raise
            logger.info(
                "traducción concurrente de la sección %s (interpretation=%s, lang=%s) "
                "ya la había persistido otra llamada; se descarta la traducción repetida",
                seccion.slug, destino.pk, destino_lang,
            )

    with transaction.atomic():
        destino.text = "\n\n".join(s.texto for s in destino.secciones.all())
        destino.completa = origen.completa
        destino.save(update_fields=["text", "completa"])
