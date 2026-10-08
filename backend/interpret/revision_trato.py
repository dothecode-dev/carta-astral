"""Juez + reparación del trato de quien lee, sección por sección.

Por qué existe: la instrucción de `interpret.trato` va en el prompt de cada
sección, pero el modelo no la cumple al 100%. Medido en staging el 08-10-2026:
un informe neutro en español salió con «podés generar vos misma el sacudón» y
«convertirte en especialista obsesivo de una sola». El mismo riesgo existe
hacia el género contrario en femenino y masculino.

Dos llamadas a `MODEL` sin razonamiento: un juez que lista los fragmentos
exactos con el género equivocado y, sólo si hay alguno, una reparación que
devuelve un par `original → corregido` por fragmento. La reparación NO
devuelve el texto: la primera versión lo hacía y, medido en staging el
08-10, reescribía fuera de los fragmentos («contra vos» → «contra vos
mismo» en un párrafo que estaba bien) sin que ningún tope de proporción lo
frenara, porque era una sola palabra. Ahora es el código el que aplica cada
par con `str.replace(original, corregido, 1)`, y sólo si `original` es uno de
los fragmentos del juez: fuera de ellos el texto queda byte-idéntico. Cada
par pasa además por reglas deterministas (no idéntico, sin saltos de línea,
sin una forma prohibida para el trato); el que no las cumple se descarta y
el resto se aplica igual.

Ante cualquier falla —el juez o la reparación no responden JSON, el LLM
falla— se devuelve el texto original: la revisión nunca hace fallar un
informe pago.

No importa django ni api (contrato de `lint-imports`).
"""

import json
import logging
import re
from collections import Counter

from interpret.exceptions import InterpretationError
from interpret.generator import _stream_text
from interpret.prompts import MODEL
from interpret.trato import instruccion

logger = logging.getLogger(__name__)

# Idiomas donde hay género que marcar. En inglés el texto no lo marca.
_IDIOMAS_CON_GENERO = ("es", "pt")

# El juez sólo devuelve una lista corta de fragmentos.
JUEZ_MAX_TOKENS = 1000

# Vueltas de juez + reparación por sección. Medido en staging: una reparación
# a veces deja el género («estás armado» → «estás armado por dentro»); una
# segunda vuelta mira el texto ya reparado. Más no: cada vuelta son dos
# llamadas, y lo que dos no corrigen se queda como estaba.
MAX_VUELTAS = 2

# La reparación devuelve sólo pares cortos (un fragmento de pocas palabras y
# su corrección), no el texto: 2000 alcanza para decenas de pares, más de los
# que el juez lista en una sección.
REPARACION_MAX_TOKENS = 2000

# Cuántos caracteres de alrededor del fragmento viajan a la reparación como
# contexto: lo justo para saber a quién se refiere, sin mandar la sección.
_CONTEXTO_CARACTERES = 80

# Formas que un `corregido` no puede traer, según el trato. Neutro: «mismo»,
# «misma», «mesmo», «mesma» como palabra suelta (es lo que más se escapa, y
# «contra vos mismo» fue el error que introdujo la primera reparación); cae
# también algún uso que no se refiere a quien lee («lo mismo»), y ese par se
# pierde: preferible a aceptar uno malo. Los oblicuos «o»/«a» del portugués
# no entran: son ambiguos con el artículo y la preposición.
_FORMAS_PROHIBIDAS = {
    "neutro": re.compile(r"\b(mismo|misma|mesmo|mesma)\b", re.IGNORECASE),
    "femenino": re.compile(r"\b(vos\s+mismo|você\s+mesmo)\b", re.IGNORECASE),
    "masculino": re.compile(r"\b(vos\s+misma|você\s+mesma)\b", re.IGNORECASE),
}

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
    "Sos un corrector. Quien lee eligió que le hablen {trato}. Te paso fragmentos de un texto "
    "donde se escapó un género que no corresponde, cada uno con unas palabras de contexto "
    "alrededor para que sepas a quién se refiere. Para cada fragmento devolvé un par: "
    "«original», el fragmento copiado EXACTAMENTE como te lo pasé, y «corregido», el mismo "
    "fragmento reformulado lo mínimo para que quede {trato}. Corregí sólo lo que está dentro "
    "del fragmento; el contexto es para entender, no para cambiar.\n\n"
    "Corregir significa reformular para que la palabra con género DESAPAREZCA o cambie: "
    "agregar palabras alrededor no corrige nada. Por ejemplo, «estás armado» → «estás armado "
    "por dentro» no sirve (agrega palabras y deja el género), «estás armado» → «estás hecho» "
    "tampoco (sigue con género); «estás armado» → «te armaste» o «tu forma de ser» sí sirve. "
    "Nunca uses barras («confundido/a»), «x», «@» ni «e» como terminación inclusiva.\n\n"
    "Respondé sólo con un JSON "
    'de la forma {{"reemplazos": [{{"original": "...", "corregido": "..."}}]}}.\n\n'
    "Cómo reformular:\n{guia}"
)

_SCHEMA_REPARACION = {
    "type": "object",
    "properties": {
        "reemplazos": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"original": {"type": "string"}, "corregido": {"type": "string"}},
                "required": ["original", "corregido"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["reemplazos"],
    "additionalProperties": False,
}


def describir_trato(trato: str) -> str:
    """Cómo se nombra el trato en los system del juez y de la reparación.
    Vacío o desconocido es neutro, igual que en `interpret.trato`."""
    return _DESCRIPCION_TRATO.get(trato) or _DESCRIPCION_TRATO["neutro"]


def _clave(trato: str) -> str:
    return trato if trato in _DESCRIPCION_TRATO else "neutro"


def _cargar_json(crudo: str):
    """Tolera un bloque ```json por si la salida estructurada no se aplicó."""
    texto = crudo.strip()
    if texto.startswith("```"):
        texto = texto.split("\n", 1)[1] if "\n" in texto else ""
        texto = texto.rsplit("```", 1)[0]
    return json.loads(texto)


def _parsear_fragmentos(crudo: str) -> list[str]:
    """La lista del juez. Levanta ValueError si no es la forma pedida."""
    datos = _cargar_json(crudo)
    fragmentos = datos.get("fragmentos") if isinstance(datos, dict) else None
    if not isinstance(fragmentos, list) or not all(isinstance(f, str) for f in fragmentos):
        raise ValueError("el juez no devolvió una lista de fragmentos")
    return fragmentos


def _parsear_reemplazos(crudo: str) -> list[tuple[str, str]]:
    """Los pares de la reparación. Levanta ValueError si no es la forma pedida."""
    datos = _cargar_json(crudo)
    pares = datos.get("reemplazos") if isinstance(datos, dict) else None
    if not isinstance(pares, list):
        raise ValueError("la reparación no devolvió una lista de reemplazos")
    resultado = []
    for par in pares:
        original = par.get("original") if isinstance(par, dict) else None
        corregido = par.get("corregido") if isinstance(par, dict) else None
        if not isinstance(original, str) or not isinstance(corregido, str):
            raise ValueError("un reemplazo no tiene original y corregido de texto")
        resultado.append((original, corregido))
    return resultado


def _con_contexto(texto: str, fragmento: str) -> str:
    i = texto.index(fragmento)
    antes = texto[max(0, i - _CONTEXTO_CARACTERES):i]
    despues = texto[i + len(fragmento):i + len(fragmento) + _CONTEXTO_CARACTERES]
    return f"- fragmento: «{fragmento}»\n  contexto: «…{antes}[[{fragmento}]]{despues}…»"


# Marcas «inclusivas» que nunca van en el informe, en ningún trato: barra entre
# letras («confundido/a», medido en staging), arroba, o una palabra terminada
# en x/xs («todxs») que no estaba ya en el original («relax» sí puede estar).
_BARRA_ENTRE_LETRAS = re.compile(r"[^\W\d_]/[^\W\d_]")
_PALABRA_EN_X = re.compile(r"\b\w+xs?\b", re.IGNORECASE)


def _marca_inclusiva(original: str, corregido: str) -> bool:
    if "@" in corregido or _BARRA_ENTRE_LETRAS.search(corregido):
        return True
    previas = {p.lower() for p in _PALABRA_EN_X.findall(original)}
    return any(p.lower() not in previas for p in _PALABRA_EN_X.findall(corregido))


_TOKEN = re.compile(r"\w+|[^\w\s]")


def _solo_agrega_palabras(original: str, corregido: str) -> bool:
    """El corregido contiene al original entero, palabra por palabra y en
    orden, con palabras agregadas en el medio o alrededor: la forma con
    género sigue ahí. Por palabras y no por substring porque el caso medido
    en staging intercala: «cómo estás armado: la manera» → «cómo estás armado
    por dentro: la manera» no contiene al original como substring."""
    restantes = iter(_TOKEN.findall(corregido.lower()))
    return all(token in restantes for token in _TOKEN.findall(original.lower()))


def _motivo_de_rechazo(original: str, corregido: str, texto: str, listados: set[str], clave: str) -> str | None:
    """Por qué un par no se aplica, o None si se aplica. Los motivos son
    claves fijas: van al log como contadores, nunca el texto."""
    if original not in listados:
        return "no_listado"
    if original not in texto:
        # Un par anterior ya lo tocó, o el modelo lo copió distinto.
        return "ausente"
    if corregido == original:
        return "identico"
    if not corregido.strip():
        return "vacio"
    if "\n" in original or "\n" in corregido:
        # Un fragmento es unas palabras dentro de una oración. Con un salto
        # de línea cruza párrafos o un título, y corregirlo podría tocar la
        # estructura markdown (lo que antes cuidaba el chequeo de encabezados).
        return "salto_de_linea"
    if _marca_inclusiva(original, corregido):
        return "marca_inclusiva"
    if _FORMAS_PROHIBIDAS[clave].search(corregido):
        return "forma_prohibida"
    # Al final: si además trae una forma prohibida, ese motivo es más preciso.
    if _solo_agrega_palabras(original, corregido):
        return "solo_agrego_palabras"
    return None


def revisar_trato(texto: str, trato: str, lang: str, client) -> str:
    """Devuelve `texto` con el trato corregido, o `texto` tal cual si no hay
    nada que corregir o si la revisión no se puede hacer con garantías.

    Hasta `MAX_VUELTAS` vueltas de juez + reparación: la segunda sólo corre
    si la primera aplicó algo, y el juez mira el texto ya reparado. Una
    vuelta que falla deja el texto como estaba al empezarla (la primera, ya
    verificada par por par, se conserva)."""
    if lang not in _IDIOMAS_CON_GENERO:
        return texto
    clave = _clave(trato)
    resultado = texto
    for vuelta in range(1, MAX_VUELTAS + 1):
        resultado, aplicados = _vuelta(resultado, clave, lang, client, vuelta)
        if not aplicados:
            break
    return resultado


def _vuelta(texto: str, clave: str, lang: str, client, vuelta: int) -> tuple[str, int]:
    """Un juez y, si lista algo, una reparación. Devuelve el texto (reparado
    o tal cual) y cuántos pares se aplicaron."""
    descripcion = describir_trato(clave)
    system_juez = [{"type": "text", "text": _SYSTEM_JUEZ.format(trato=descripcion, que_listar=_QUE_LISTAR[clave])}]
    try:
        crudo = _stream_text(
            client, MODEL, system_juez, texto, JUEZ_MAX_TOKENS,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA_JUEZ}},
        )
        fragmentos = _parsear_fragmentos(crudo)
    except InterpretationError as exc:
        logger.warning(
            "revisión del trato: falló el juez, se deja el texto: vuelta=%s trato=%s lang=%s error=%s",
            vuelta, clave, lang, exc,
        )
        return texto, 0
    except ValueError as exc:  # json.JSONDecodeError es ValueError
        logger.warning(
            "revisión del trato: el juez no devolvió JSON válido, se deja el texto: vuelta=%s trato=%s lang=%s error=%s",
            vuelta, clave, lang, exc,
        )
        return texto, 0

    # Un fragmento que no está en el texto es una invención del juez: no hay
    # nada que reparar ahí y pedirlo sólo invita a la reparación a tocar otra cosa.
    presentes = [f for f in dict.fromkeys(fragmentos) if f and f in texto]
    if len(presentes) < len(fragmentos):
        logger.info(
            "revisión del trato: el juez listó fragmentos que no están en el texto: vuelta=%s descartados=%s",
            vuelta, len(fragmentos) - len(presentes),
        )
    if not presentes:
        return texto, 0

    system_reparacion = [{
        "type": "text",
        "text": _SYSTEM_REPARACION.format(trato=descripcion, guia=instruccion(clave, lang)),
    }]
    contenido = "\n".join(_con_contexto(texto, f) for f in presentes)
    try:
        crudo = _stream_text(
            client, MODEL, system_reparacion, contenido, REPARACION_MAX_TOKENS,
            thinking={"type": "disabled"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA_REPARACION}},
        )
        pares = _parsear_reemplazos(crudo)
    except InterpretationError as exc:
        logger.warning(
            "revisión del trato: falló la reparación, se deja el texto: vuelta=%s trato=%s lang=%s fragmentos=%s error=%s",
            vuelta, clave, lang, len(presentes), exc,
        )
        return texto, 0
    except ValueError as exc:  # json.JSONDecodeError es ValueError
        logger.warning(
            "revisión del trato: la reparación no devolvió JSON válido, se deja el texto: "
            "vuelta=%s trato=%s lang=%s fragmentos=%s error=%s",
            vuelta, clave, lang, len(presentes), exc,
        )
        return texto, 0

    listados = set(presentes)
    rechazos: Counter[str] = Counter()
    aplicados = 0
    resultado = texto
    for original, corregido in pares:
        if motivo := _motivo_de_rechazo(original, corregido, resultado, listados, clave):
            rechazos[motivo] += 1
            continue
        resultado = resultado.replace(original, corregido, 1)
        listados.discard(original)  # un fragmento se corrige una sola vez
        aplicados += 1

    detalle = " ".join(f"{motivo}={n}" for motivo, n in sorted(rechazos.items()))
    nivel = logging.WARNING if rechazos else logging.INFO
    logger.log(
        nivel,
        "revisión del trato: vuelta=%s listados=%s aplicados=%s rechazados=%s %s trato=%s lang=%s",
        vuelta, len(presentes), aplicados, sum(rechazos.values()), detalle, clave, lang,
    )
    return resultado, aplicados
