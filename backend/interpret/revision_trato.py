"""Juez + reparación del trato de quien lee, sección por sección.

Por qué existe: la instrucción de `interpret.trato` va en el prompt de cada
sección, pero el modelo no la cumple al 100%. Medido en staging el 08-10-2026:
un informe neutro en español salió con «podés generar vos misma el sacudón» y
«convertirte en especialista obsesivo de una sola». El mismo riesgo existe
hacia el género contrario en femenino y masculino.

Dos llamadas a `MODEL` sin razonamiento: un juez que lista los fragmentos
exactos con el género equivocado y, sólo si hay alguno, una reparación que
corrige esos fragmentos y nada más. La reparación se verifica de forma
determinista antes de aceptarla (no vacía, mismos encabezados, cambio
acotado). Ante cualquier duda —el juez no responde JSON, el LLM falla, la
reparación se pasa— se devuelve el texto original: la revisión nunca hace
fallar un informe pago, y un texto con un «vos misma» suelto es mejor que
uno reescrito sin control.

No importa django ni api (contrato de `lint-imports`).
"""

import difflib
import json
import logging

from interpret.exceptions import InterpretationError
from interpret.generator import _stream_text
from interpret.prompts import MODEL, TRANSLATE_MAX_TOKENS_GENERACION
from interpret.trato import instruccion

logger = logging.getLogger(__name__)

# Idiomas donde hay género que marcar. En inglés el texto no lo marca.
_IDIOMAS_CON_GENERO = ("es", "pt")

# El juez sólo devuelve una lista corta de fragmentos.
JUEZ_MAX_TOKENS = 1000

# Proporción máxima de palabras que la reparación puede cambiar respecto del
# original. Corregir un fragmento toca 1-3 palabras («vos misma» → «por tu
# cuenta»); una sección de 900 palabras con 10 fragmentos mal cambia ~30, un
# 3%. El 5% deja margen para eso y frena una reparación que reescribió
# párrafos enteros —que es justo lo que no se le pidió—.
MAX_PROPORCION_CAMBIADA = 0.05

_DESCRIPCION_TRATO = {
    "femenino": "en femenino",
    "masculino": "en masculino",
    "neutro": "en neutro, sin marcar género",
}

_QUE_LISTAR = {
    "femenino": "las formas MASCULINAS referidas a quien lee (por ejemplo «vos mismo», "
                "«seguro», «cansado», «você mesmo», «o empurra»)",
    "masculino": "las formas FEMENINAS referidas a quien lee (por ejemplo «vos misma», "
                 "«segura», «cansada», «você mesma», «a empurra»)",
    "neutro": "CUALQUIER marca de género referida a quien lee: adjetivos y participios "
              "terminados en -o/-a («seguro», «segura», «obsesivo», «dispuesta»), «vos "
              "mismo/misma», «você mesmo/mesma», «consigo mesmo/mesma», «sozinho/sozinha», "
              "y en portugués los pronombres oblicuos «o»/«a» referidos a quien lee («o "
              "empurra», «a torna»)",
}

_SYSTEM_JUEZ = (
    "Sos un corrector que revisa el género gramatical con que un texto se dirige a quien lo "
    "lee. El texto es una interpretación astrológica en español o portugués. Quien lee eligió "
    "que le hablen {trato}.\n\n"
    "Listá los fragmentos del texto donde un adjetivo, participio o pronombre referido a QUIEN "
    "LEE marca un género que no corresponde. Hay que listar {que_listar}.\n\n"
    "NO listes lo que concuerda con otra cosa: un planeta («la Luna es protectora»), un signo, "
    "un lugar, un sustantivo («una persona capaz»), «la otra persona», la pareja, la madre, el "
    "padre u otros terceros. Ante la duda sobre a quién se refiere una palabra, no la listes.\n\n"
    "Cada fragmento tiene que estar copiado EXACTAMENTE como aparece en el texto, carácter por "
    "carácter, con unas pocas palabras alrededor para que sea único. Si no hay ninguno, la "
    'lista va vacía. Respondé sólo con un JSON de la forma {{"fragmentos": ["...", "..."]}}.'
)

_SCHEMA_JUEZ = {
    "type": "object",
    "properties": {"fragmentos": {"type": "array", "items": {"type": "string"}}},
    "required": ["fragmentos"],
    "additionalProperties": False,
}

_SYSTEM_REPARACION = (
    "Sos un corrector. Quien lee este texto eligió que le hablen {trato}. Te paso el texto "
    "completo y una lista de fragmentos donde se escapó un género que no corresponde. Corregí "
    "SÓLO esos fragmentos para que queden {trato}, reformulando lo mínimo. No cambies ninguna "
    "otra palabra, ni la puntuación, ni los saltos de línea, ni el formato markdown (títulos "
    "con #, negritas, listas). Devolvé el texto completo corregido y nada más: sin comentarios, "
    "sin explicaciones, sin bloques de código.\n\n"
    "Cómo reformular:\n{guia}"
)


def describir_trato(trato: str) -> str:
    """Cómo se nombra el trato en los system del juez y de la reparación.
    Vacío o desconocido es neutro, igual que en `interpret.trato`."""
    return _DESCRIPCION_TRATO.get(trato) or _DESCRIPCION_TRATO["neutro"]


def _clave(trato: str) -> str:
    return trato if trato in _DESCRIPCION_TRATO else "neutro"


def _parsear_fragmentos(crudo: str) -> list[str]:
    """La lista del juez. Tolera un bloque ```json por si la salida
    estructurada no se aplicó. Levanta ValueError si no es la forma pedida."""
    texto = crudo.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    datos = json.loads(texto)
    fragmentos = datos.get("fragmentos") if isinstance(datos, dict) else None
    if not isinstance(fragmentos, list) or not all(isinstance(f, str) for f in fragmentos):
        raise ValueError("el juez no devolvió una lista de fragmentos")
    return fragmentos


def _encabezados(texto: str) -> list[str]:
    return [linea.rstrip() for linea in texto.splitlines() if linea.startswith("#")]


def _proporcion_cambiada(original: str, reparado: str) -> float:
    a, b = original.split(), reparado.split()
    if not a:
        return 1.0
    # autojunk=False: con más de 200 palabras, el default trata como basura
    # las más frecuentes («de», «la», «que») y el emparejamiento sale peor.
    iguales = sum(m.size for m in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())
    return (max(len(a), len(b)) - iguales) / len(a)


def _motivo_de_rechazo(original: str, reparado: str) -> str | None:
    if not reparado.strip():
        return "reparación vacía"
    if _encabezados(reparado) != _encabezados(original):
        return "la reparación cambió los encabezados"
    proporcion = _proporcion_cambiada(original, reparado)
    if proporcion > MAX_PROPORCION_CAMBIADA:
        return f"la reparación cambió demasiado ({proporcion:.1%} de las palabras)"
    return None


def revisar_trato(texto: str, trato: str, lang: str, client) -> str:
    """Devuelve `texto` con el trato corregido, o `texto` tal cual si no hay
    nada que corregir o si la revisión no se puede hacer con garantías."""
    if lang not in _IDIOMAS_CON_GENERO:
        return texto
    clave = _clave(trato)
    descripcion = describir_trato(trato)

    system_juez = [{"type": "text", "text": _SYSTEM_JUEZ.format(trato=descripcion, que_listar=_QUE_LISTAR[clave])}]
    try:
        crudo = _stream_text(
            client, MODEL, system_juez, texto, JUEZ_MAX_TOKENS,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA_JUEZ}},
        )
        fragmentos = _parsear_fragmentos(crudo)
    except InterpretationError as exc:
        logger.warning("revisión del trato: falló el juez, se deja el texto: trato=%s lang=%s error=%s", clave, lang, exc)
        return texto
    except ValueError as exc:  # json.JSONDecodeError es ValueError
        logger.warning(
            "revisión del trato: el juez no devolvió JSON válido, se deja el texto: trato=%s lang=%s error=%s",
            clave, lang, exc,
        )
        return texto

    # Un fragmento que no está en el texto es una invención del juez: no hay
    # nada que reparar ahí y pedirlo sólo invita a la reparación a tocar otra cosa.
    presentes = [f for f in dict.fromkeys(fragmentos) if f and f in texto]
    if len(presentes) < len(fragmentos):
        logger.info(
            "revisión del trato: el juez listó fragmentos que no están en el texto: descartados=%s",
            len(fragmentos) - len(presentes),
        )
    if not presentes:
        return texto

    system_reparacion = [{
        "type": "text",
        "text": _SYSTEM_REPARACION.format(trato=descripcion, guia=instruccion(clave, lang)),
    }]
    lista = "\n".join(f"- «{f}»" for f in presentes)
    contenido = f"<fragmentos>\n{lista}\n</fragmentos>\n\n<texto>\n{texto}\n</texto>"
    try:
        reparado = _stream_text(
            client, MODEL, system_reparacion, contenido, TRANSLATE_MAX_TOKENS_GENERACION,
            thinking={"type": "disabled"},
        )
    except InterpretationError as exc:
        logger.warning(
            "revisión del trato: falló la reparación, se deja el texto: trato=%s lang=%s fragmentos=%s error=%s",
            clave, lang, len(presentes), exc,
        )
        return texto

    # Si el modelo devolvió el texto con la etiqueta con que se lo pasamos,
    # se la saca: dos palabras de más pasan el tope de cambio y quedarían
    # guardadas en el informe.
    if reparado.startswith("<texto>") and reparado.endswith("</texto>"):
        reparado = reparado[len("<texto>"):-len("</texto>")].strip()

    if motivo := _motivo_de_rechazo(texto, reparado):
        logger.warning(
            "revisión del trato: reparación rechazada, se deja el texto: trato=%s lang=%s fragmentos=%s motivo=%s",
            clave, lang, len(presentes), motivo,
        )
        return texto
    logger.info("revisión del trato: reparación aceptada: trato=%s lang=%s fragmentos=%s", clave, lang, len(presentes))
    return reparado
