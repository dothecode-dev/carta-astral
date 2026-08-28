"""Armado del informe de ocho secciones.

Vive fuera de `views.py` porque `api/` ya es grande y la lógica va en módulos
de servicio. La propiedad que sostiene todo lo demás es que **cada sección se
guarda apenas se termina**: eso es lo que hace la generación reanudable sin
agregar una cola de trabajos, y lo que impide pagarle dos veces al modelo por
el mismo párrafo.
"""

import logging

from django.db import transaction

from api.interpretation_service import renovar_lock
from api.models import InterpretationSection
from interpret.generator import build_seccion
from interpret.prompts import SECCIONES, Seccion

logger = logging.getLogger(__name__)

# Cuánto de cada sección ya escrita viaja como contexto de la siguiente. El
# informe entero no entra en el prompt; el primer párrafo alcanza para que no
# se repitan y mantiene el input acotado.
RESUMEN_POR_SECCION = 400


def secciones_aplicables(chart) -> list[Seccion]:
    """Las ocho, menos las que dependen de una hora de nacimiento que no está."""
    hora = chart.data.get("time_known", True)
    return [s for s in SECCIONES if hora or not s.requiere_hora]


def secciones_pendientes(interpretacion) -> list[Seccion]:
    hechas = set(interpretacion.secciones.values_list("slug", flat=True))
    return [s for s in secciones_aplicables(interpretacion.chart) if s.slug not in hechas]


def resumen_previo(interpretacion) -> str:
    return "\n\n".join(
        s.texto[:RESUMEN_POR_SECCION] for s in interpretacion.secciones.all()
    )


def resumen_gratis(interpretacion) -> list[dict]:
    """Lo que ve quien no pagó: el índice completo y el arranque de cada
    sección (RF3).

    No es la primera sección recortada. La primera sección es Sol, Luna y
    Ascendente —justo lo que más le importa a la gente—, y regalarla entera
    hace que quien la lee ya no tenga por qué pagar.

    El índice sale de `secciones_aplicables(chart)` —el catálogo, filtrado
    por si hay hora de nacimiento—, no de `interpretacion.secciones.all()`.
    La generación corre fuera del request y es reanudable (RF10): este
    resumen tiene que poder mostrarse con el informe a medio generar, y
    tiene que nombrar las ocho secciones (o las siete que aplican sin hora)
    aunque todavía falten por escribirse. Las que no están generadas
    todavía aparecen con su título y sin párrafo.
    """
    generadas = {s.slug: s for s in interpretacion.secciones.all()}
    salida = []
    for seccion in secciones_aplicables(interpretacion.chart):
        existente = generadas.get(seccion.slug)
        if existente is None:
            parrafo, restante = "", seccion.palabras
        else:
            parrafo, _, resto = existente.texto.partition("\n\n")
            parrafo, restante = parrafo.strip(), len(resto.split())
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
    lock de esta carta (el token de `get_or_create_interpretation`, o el que
    tome el flujo equivalente del informe). Después de persistir CADA sección
    se llama a `renovar_lock(chart, token)`: un informe son ocho llamadas
    secuenciales de hasta 1000 palabras, unos 6 minutos contra un
    `LOCK_TTL = 600`, así que sin renovar el lock la generación sobrevive a su
    propio candado. Si `renovar_lock` devuelve `False` el lock YA NO ES
    NUESTRO —otro proceso lo tomó porque el nuestro expiró— y esa función
    aborta de forma limpia: no sigue pidiendo secciones, no marca `completa`,
    no toca el ledger. Seguir generando en ese momento significaría dos
    procesos escribiendo las mismas secciones.

    Contrato de crédito para quien llama (hoy nadie; la Tarea 10 es quien
    decide si cobra y si devuelve, no esta función):

    - Esta función NUNCA llama a `ledger.devolver`. No le corresponde: genera
      y persiste, no decide sobre plata. Ni siquiera cuando pierde el lock —
      perder el lock no es que el informe se haya arruinado, es que otro
      proceso lo sigue y probablemente lo termine.
    - `get_or_create_interpretation` cobra un crédito la primera vez que la
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
    aplicables = secciones_aplicables(interpretacion.chart)
    orden_por_slug = {seccion.slug: indice for indice, seccion in enumerate(aplicables)}

    for seccion in secciones_pendientes(interpretacion):
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
        if not renovar_lock(interpretacion.chart, token):
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
