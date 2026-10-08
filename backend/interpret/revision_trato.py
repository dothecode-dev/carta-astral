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
par en su única aparición como palabras completas, y sólo si `original` es uno de
los fragmentos del juez: fuera de ellos el texto queda byte-idéntico. Cada
par pasa además por reglas deterministas (no idéntico, sin saltos de línea,
sin una forma prohibida para el trato); el que no las cumple se descarta y
el resto se aplica igual.

Ante cualquier falla —el juez o la reparación no responden JSON, el LLM
falla— se devuelve el texto original: la revisión nunca hace fallar un
informe pago.

No importa django ni api (contrato de `lint-imports`).
"""

import difflib
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

# Un fragmento del juez con más palabras que esto no se repara. Medido en
# staging (8ef370d): el juez listó casi un párrafo y la reparación lo
# reescribió entero, despersonalizado («Vivís entre esas dos» → «Hay un vivir
# entre esas dos»). Un escape de género es una o dos palabras; 12 deja
# contexto para que sea único y corta los fragmentos-párrafo.
MAX_PALABRAS_FRAGMENTO = 12

# Cuántas palabras puede cambiar un par (borradas + agregadas + reemplazadas,
# cada reemplazo contado por el lado más largo). «vos misma» → «por tu
# cuenta» son 3; «estás armado» → «te armaste», 2. Más de 4 ya es reescribir,
# no corregir un género.
MAX_PALABRAS_CAMBIADAS = 4

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
    "Mantené la segunda persona: el texto le habla a quien lee, y cada «te», «tu», «vos», "
    "«você» o verbo en voseo del original tiene que seguir estando. Cambiá la menor cantidad "
    "de palabras posible, idealmente sólo la que marca género. Nunca reescribas con "
    "construcciones impersonales: «Vivís entre esas dos» → «hay un vivir entre esas dos» o "
    "«naciste con» → «hubo un nacer con» están mal.\n\n"
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


def _patron(fragmento: str) -> re.Pattern[str]:
    """El fragmento como palabras completas. Buscar subcadenas encontraba «el
    protector» dentro de «del protector» y lo dejaba como «dla protectora»
    (code review sobre cf25337); igual «o sonhador» en «ao sonhador». Con
    `re`, `\\w` ya es Unicode, así que «ó» o «ç» cuentan como letra."""
    return re.compile(rf"(?<!\w){re.escape(fragmento)}(?!\w)")


def _apariciones(texto: str, fragmento: str) -> int:
    return len(_patron(fragmento).findall(texto))


def _reemplazar(texto: str, original: str, corregido: str) -> str:
    # Función de reemplazo y no el string: una barra invertida en `corregido`
    # no se interpreta como referencia a un grupo.
    return _patron(original).sub(lambda _: corregido, texto, count=1)


def _con_contexto(texto: str, fragmento: str) -> str:
    coincidencia = _patron(fragmento).search(texto)
    if coincidencia is None:  # no pasa: sólo se llama con fragmentos presentes
        return f"- fragmento: «{fragmento}»"
    i = coincidencia.start()
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


# Marcas de segunda persona. Una corrección que tiene menos que el original
# despersonalizó («que no te pida endurecerte» → «que no pida endurecerse»,
# «tu camino» → «el camino», medido en staging). El voseo se aproxima con
# palabras de 4 letras o más terminadas en -ás/-és/-ís («vivís», «podés»,
# «estás»): cae también algún «además», «después» o «país», pero como se
# comparan cuentas del mismo fragmento antes y después, una palabra que no
# cambió suma igual de los dos lados. Los enclíticos («endurecerte») no se
# cuentan.
_SEGUNDA_PERSONA = {
    "es": frozenset({"te", "tu", "tus", "vos", "ti", "contigo", "tuyo", "tuya", "tuyos", "tuyas"}),
    "pt": frozenset({"você", "te", "seu", "sua", "seus", "suas", "si", "contigo"}),
}
_VOSEO = re.compile(r"^\w{2,}(ás|és|ís)$")
_PALABRA = re.compile(r"\w+")


def _marcas_segunda_persona(texto: str, lang: str) -> int:
    pronombres = _SEGUNDA_PERSONA[lang]
    marcas = 0
    for palabra in _PALABRA.findall(texto.lower()):
        if palabra in pronombres or (lang == "es" and _VOSEO.match(palabra)):
            marcas += 1
    return marcas


def _diferencias(original: str, corregido: str):
    a, b = original.split(), corregido.split()
    opcodes = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    return a, [op for op in opcodes if op[0] != "equal"]


def _palabras_cambiadas(original: str, corregido: str) -> int:
    _, distintas = _diferencias(original, corregido)
    return sum(max(i2 - i1, j2 - j1) for _, i1, i2, j1, j2 in distintas)


# Qué cuenta como palabra con género. La regla es aproximada en UNA sola
# dirección: puede dejar pasar algún retoque de más («para», «hacia», «tenés»
# también cuentan), pero nunca tiene que rechazar una corrección real.
# Terminaciones: -o/-a/-os/-as, -or/-ora/-ores/-oras («soñador» →
# «soñadora»), -ón/-ona/-ones/-onas, -án/-ana («guardián»), -ín/-ina
# («bailarín»), -ol/-ola («español»), -és/-esa y el -ês/-esa del portugués
# («português»). Las femeninas ya caen en -a/-as.
_GENERO = re.compile(r"(o|a|os|as|or|ores|ón|ones|án|ín|ol|és|ês)$")
# Determinantes y pronombres con género, aunque no terminen así («un» →
# «una», «el protector» → «la protectora», «um sonhador» → «uma
# sonhadora»). Incluye «o»/«a» del portugués («Áries o empurra»).
_DETERMINANTES_CON_GENERO = frozenset({
    "un", "una", "unos", "unas", "el", "la", "los", "las",
    "um", "uma", "uns", "umas", "o", "a", "os", "as",
    "aquel", "aquella", "este", "esta", "ese", "esa",
    "ele", "ela", "él", "ella",
})
_PUNTUACION_PEGADA = re.compile(r"^\W+|\W+$")


def _cambia_palabra_con_genero(original: str, corregido: str) -> bool:
    """Alguna de las palabras del ORIGINAL que la corrección borra o
    reemplaza termina en género. Medido en staging (9a22a6e): el juez marcó
    frases sin género y la reparación las retocó igual («Vivís» →
    «Transitás», «permeabilidad» → «apertura», «naciste con» → «tenés»)."""
    a, distintas = _diferencias(original, corregido)
    for _, i1, i2, _, _ in distintas:
        for palabra in a[i1:i2]:
            limpia = _PUNTUACION_PEGADA.sub("", palabra.lower())
            if limpia in _DETERMINANTES_CON_GENERO or _GENERO.search(limpia):
                return True
    return False


_TOKEN = re.compile(r"\w+|[^\w\s]")


def _solo_agrega_palabras(original: str, corregido: str) -> bool:
    """El corregido contiene al original entero, palabra por palabra y en
    orden, con palabras agregadas en el medio o alrededor: la forma con
    género sigue ahí. Por palabras y no por substring porque el caso medido
    en staging intercala: «cómo estás armado: la manera» → «cómo estás armado
    por dentro: la manera» no contiene al original como substring."""
    restantes = iter(_TOKEN.findall(corregido.lower()))
    return all(token in restantes for token in _TOKEN.findall(original.lower()))


def _motivo_de_rechazo(
    original: str, corregido: str, texto: str, listados: set[str], clave: str, lang: str
) -> str | None:
    """Por qué un par no se aplica, o None si se aplica. Los motivos son
    claves fijas: van al log como contadores, nunca el texto."""
    if original not in listados:
        return "no_listado"
    apariciones = _apariciones(texto, original)
    if apariciones == 0:
        # Un par anterior ya lo tocó, o el modelo lo copió distinto.
        return "ausente"
    if apariciones > 1:
        # `replace(..., 1)` tocaría la primera aparición, que puede no ser la
        # mal escrita; pasa si un corregido ya aplicado trae este texto.
        return "no_unico"
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
    if _marcas_segunda_persona(corregido, lang) < _marcas_segunda_persona(original, lang):
        return "despersonaliza"
    if _palabras_cambiadas(original, corregido) > MAX_PALABRAS_CAMBIADAS:
        return "cambio_grande"
    # Al final: si además trae una forma prohibida, ese motivo es más preciso.
    if _solo_agrega_palabras(original, corregido):
        return "solo_agrego_palabras"
    if not _cambia_palabra_con_genero(original, corregido):
        return "sin_genero"
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

    # Sólo fragmentos que aparecen exactamente una vez. Uno que no está es una
    # invención del juez: pedir repararlo invita a tocar otra cosa. Uno que
    # aparece más de una vez («seguro» en «es seguro que Saturno» y en «estás
    # seguro») no se puede reparar con garantías: `replace(..., 1)` y el
    # contexto toman la primera aparición, que puede ser la que estaba bien.
    # Vale también para frases: reemplazar todas las copias (19a0287) cambia
    # subcadenas («del protector» → «dla protectora», «ao sonhador» → «aa
    # sonhadora») y copias que no se refieren a quien lee («Saturno es el
    # protector»). Y uno de más de `MAX_PALABRAS_FRAGMENTO` palabras invita a
    # reescribir.
    unicos = list(dict.fromkeys(f for f in fragmentos if f))
    largos = [f for f in unicos if len(f.split()) > MAX_PALABRAS_FRAGMENTO]
    cortos = [f for f in unicos if len(f.split()) <= MAX_PALABRAS_FRAGMENTO]
    cuentas = {f: _apariciones(texto, f) for f in cortos}
    ausentes = sum(1 for f in cortos if cuentas[f] == 0)
    no_unicos = sum(1 for f in cortos if cuentas[f] > 1)
    presentes = [f for f in cortos if cuentas[f] == 1]
    if largos or ausentes or no_unicos:
        logger.info(
            "revisión del trato: fragmentos del juez descartados: vuelta=%s largo=%s ausente=%s no_unico=%s",
            vuelta, len(largos), ausentes, no_unicos,
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
        if motivo := _motivo_de_rechazo(original, corregido, resultado, listados, clave, lang):
            rechazos[motivo] += 1
            continue
        resultado = _reemplazar(resultado, original, corregido)
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
