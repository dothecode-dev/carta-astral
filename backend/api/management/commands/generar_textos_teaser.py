"""Genera los textos fijos del teaser: un párrafo por cuerpo y signo.

El teaser de la lectura breve gratis no llama al modelo en runtime: lee un
JSON revisado a mano. Este comando produce el borrador de ese JSON, y es de
desarrollo: se corre una vez por idioma, Gustavo revisa el resultado, y recién
entonces se commitea. No corre en tests contra la API real ni en producción.

    python manage.py generar_textos_teaser --lang es
    python manage.py generar_textos_teaser --lang en --desde es

Sin `--desde` escribe un párrafo nuevo por cada `cuerpo|signo`. Con `--desde`
traduce los textos ya revisados de ese idioma, para que el contenido sea el
mismo en los tres. Escribe `{lang: {"Sun|Ari": "...", ...}}` y no toca los
otros idiomas del archivo.
"""

import json
import logging
import pathlib
import re
from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from api.firma_frases import IDIOMAS, SIGNOS, nombre_signo
from api.interpretation_service import _build_client
from api.teaser import CUERPOS_TEASER
from interpret.exceptions import InterpretationError
from interpret.generator import _stream_text
from interpret.prompts import MODEL

logger = logging.getLogger(__name__)

RUTA_DEFAULT = pathlib.Path(__file__).resolve().parents[2] / "data" / "teaser_textos.json"

MAX_TOKENS = 600
PALABRAS_MIN, PALABRAS_MAX = 50, 110
# Veces que se vuelve a pedir un texto con problemas, además del primer intento.
REINTENTOS = 3

_CUERPO = {
    "es": {"Sun": "el Sol", "Moon": "la Luna", "Ascendant": "el Ascendente",
           "Mercury": "Mercurio", "Venus": "Venus", "Mars": "Marte"},
    "en": {"Sun": "the Sun", "Moon": "the Moon", "Ascendant": "the Ascendant",
           "Mercury": "Mercury", "Venus": "Venus", "Mars": "Mars"},
    "pt": {"Sun": "o Sol", "Moon": "a Lua", "Ascendant": "o Ascendente",
           "Mercury": "Mercúrio", "Venus": "Vênus", "Mars": "Marte"},
}

# «Marte en Aries» / «Mars in Aries» / «Marte em Áries»: la preposición también
# es del idioma de destino.
_PREPOSICION = {"es": "en", "en": "in", "pt": "em"}

# Muletillas que la primera tanda real repitió en decenas de los 72 textos (medido
# en es: «te cuesta» en 30, «antes de» en 30, «tu identidad se construye» en 7).
# Una persona lee 6 párrafos, así que cada una se nota. Los prompts las prohíben y
# `muletillas_presentes` cuenta cuántas se colaron igual. Van en minúsculas porque se
# buscan sin distinguir mayúsculas; las fórmulas de apertura se listan por cuerpo.
_MULETILLAS_EN_CUERPO: dict[str, tuple[str, ...]] = {
    "es": (
        "te cuesta", "tu identidad se construye", "sin pedir permiso", "el desafío está en",
        "tu mundo emocional", "funciona como", "a veces",
    ),
    "en": (
        "it's hard for you", "you struggle to", "your identity is built", "without asking permission",
        "the challenge is", "your emotional world", "works like", "sometimes",
    ),
    "pt": (
        "te custa", "sua identidade se constrói", "sem pedir permissão", "o desafio está em",
        "seu mundo emocional", "funciona como", "às vezes",
    ),
}

# Fórmulas de apertura: sólo molestan al inicio del párrafo («Con Venus en…»); en
# medio de una frase son castellano normal, así que se buscan únicamente ahí.
_APERTURAS: dict[str, tuple[str, ...]] = {
    "es": (
        "con el sol en", "con la luna en", "con el ascendente en", "con mercurio en",
        "con venus en", "con marte en", "tenés el",
    ),
    "en": (
        "with the sun in", "with the moon in", "with the ascendant in", "with mercury in",
        "with venus in", "with mars in", "you have the",
    ),
    "pt": (
        "com o sol em", "com a lua em", "com o ascendente em", "com mercúrio em",
        "com vênus em", "com marte em", "você tem o",
    ),
}

MULETILLAS: dict[str, tuple[str, ...]] = {
    lang: _MULETILLAS_EN_CUERPO[lang] + _APERTURAS[lang] for lang in _MULETILLAS_EN_CUERPO
}

# Palabras que no cuentan como repetición: un n-grama hecho sólo de estas («de la
# que») aparece en cualquier texto y no es una muletilla.
_VACIAS = frozenset(
    "el la los las un una unos unas lo al del de a en con por para sin sobre entre y e o u ni que se "
    "te me le les nos su tu mi es son está the an of to in on at for with by from and or but nor "
    "that it its your you o os as um uma uns umas da das do dos no na nos nas ao aos em num numa "
    "pelo pela pelos pelas e ou mas seu sua seus suas teu tua lhe".split()
)

_PROHIBIDAS = {
    "es": (
        "Prohibido usar estas muletillas, que ya se repiten en otros textos: «te cuesta», «tu identidad "
        "se construye», «sin pedir permiso», «el desafío está en», «tu mundo emocional», «funciona como», "
        "«a veces». Prohibidas también las aperturas con fórmula: «Con Venus en…», «Tenés el Sol en…», "
        "«Marte en Aries:». "
    ),
    "en": (
        "Do NOT use these stock phrases, which already repeat across other texts: \u201cit's hard for "
        "you\u201d, \u201cyou struggle to\u201d, \u201cyour identity is built\u201d, \u201cwithout "
        "asking permission\u201d, \u201cthe challenge is\u201d, \u201cyour emotional world\u201d, "
        "\u201cworks like\u201d, \u201csometimes\u201d. Also avoid formula openings such as "
        "\u201cWith Venus in\u2026\u201d, \u201cYou have the Sun in\u2026\u201d or "
        "\u201cMars in Aries:\u201d. "
    ),
    "pt": (
        "Proibido usar estas muletas, que já se repetem em outros textos: «te custa», «sua identidade se "
        "constrói», «sem pedir permissão», «o desafio está em», «seu mundo emocional», «funciona como», "
        "«às vezes». Proibidas também as aberturas de fórmula: «Com Vênus em…», «Você tem o Sol em…», "
        "«Marte em Áries:». "
    ),
}

# Sólo para generar: el traductor ve un solo párrafo ya revisado y tiene que
# conservarlo, así que no se le pide variar la apertura.
_APERTURA_VARIADA = {
    "es": (
        "La primera frase entra directo por una imagen o un rasgo concreto de esa posición, sin "
        "nombrar la posición, y cada texto abre distinto. "
    ),
    "en": (
        "The first sentence goes straight into a concrete image or trait of that placement, "
        "without naming the placement, and every text opens differently. "
    ),
    "pt": (
        "A primeira frase entra direto por uma imagem ou um traço concreto dessa posição, sem "
        "nomear a posição, e cada texto abre de um jeito diferente. "
    ),
}

# Un texto que marca género obliga a quien lee a leerse en masculino o femenino, y
# la primera tanda lo hizo seis veces. La técnica es reescribir con verbos o con la
# voz de quien hace algo a la persona, y no atribuir rasgos a un género.
_REGLA_GENERO = {
    "es": (
        "Redacción neutra en género: nunca uses adjetivos, participios ni pronombres con género referidos "
        "a la persona que lee (nada terminado en -o/-a para ella: ni «segura» ni «seguro», ni «vos misma»). "
        "La técnica: pasá la idea a un verbo conjugado o a un sustantivo, o poné a la persona como sujeto de "
        "una acción. Ejemplos: «no querer pasar inadvertido» pasa a «preferís que te noten»; «quedarte "
        "quieto» pasa a «frenar»; «ser conquistado» pasa a «que te conquisten»; «ser dura con» pasa a "
        "«exigirle mucho a». Tampoco atribuyas rasgos a un género («maternal», «femenino», «viril»). "
        "Sin barras, «x», «@» ni «e» neutra. "
    ),
    "pt": (
        "Redação neutra em gênero: nunca use adjetivos, particípios nem pronomes com gênero referidos a quem "
        "lê (nada terminado em -o/-a para essa pessoa: nem «segura» nem «seguro», nem «você mesma»; nem "
        "«o»/«a» como pronome oblíquo: use «te» ou «lhe»). A técnica: passe a ideia para um verbo conjugado "
        "ou um substantivo, ou ponha a pessoa como sujeito de uma ação. Exemplos: «não querer passar "
        "despercebido» vira «você prefere que reparem em você»; «ficar parado» vira «parar»; «ser "
        "conquistado» vira «que te conquistem»; «ser dura com» vira «exigir muito de». Também não atribua "
        "traços a um gênero («maternal», «feminino», «viril»). Sem barras, «x», «@» nem «e» neutro. "
    ),
}

# Un prompt por idioma, escrito en ese idioma, con la regla de género y el
# ejemplo de la voz en ese idioma: con uno solo en español, el inglés y el
# portugués salían con calcos del voseo. En inglés no hay regla de género.
# Se formatean con `.format(cuerpo=, signo=)`: ninguna llave suelta.
_SISTEMA_GENERAR = {
    "es": (
        "Escribís textos para la vista previa gratuita de una carta natal. Un párrafo de 60 a 90 "
        "palabras, en español rioplatense (voseo), sobre qué significa tener {cuerpo} en {signo}. "
        "Hablale a la persona en segunda persona, con tono cálido y directo, como las frases cortas "
        "de una carta natal («Arrancás antes que nadie: lo tuyo es moverte primero y ajustar después…»). "
        "Sin promesas ni predicciones: describí tendencias, no lo que va a pasar. "
        + _PROHIBIDAS["es"]
        + _APERTURA_VARIADA["es"]
        + _REGLA_GENERO["es"]
        + "Devolvé SOLO el párrafo, sin título, sin comillas ni comentarios."
    ),
    "en": (
        "You write texts for the free preview of a natal chart. One paragraph of 60 to 90 words, "
        "in English, about what it means to have {cuerpo} in {signo}. Address the reader in the second "
        "person, in a warm, direct tone, like the short lines of a natal chart reading "
        "(\u201cYou start before anyone else: you move first and adjust later\u2026\u201d). "
        "No promises and no predictions: describe tendencies, not what will happen. "
        + _PROHIBIDAS["en"]
        + _APERTURA_VARIADA["en"]
        + "Return ONLY the paragraph, with no title, quotation marks or comments."
    ),
    "pt": (
        "Você escreve textos para a prévia gratuita de um mapa natal. Um parágrafo de 60 a 90 "
        "palavras, em português brasileiro, sobre o que significa ter {cuerpo} em {signo}. "
        "Fale com a pessoa em segunda pessoa (você), com tom caloroso e direto, como as frases curtas "
        "de um mapa natal («Você começa antes de todo mundo: seu jeito é se mover primeiro e ajustar depois…»). "
        "Sem promessas nem previsões: descreva tendências, não o que vai acontecer. "
        + _PROHIBIDAS["pt"]
        + _APERTURA_VARIADA["pt"]
        + _REGLA_GENERO["pt"]
        + "Devolva SÓ o parágrafo, sem título, aspas nem comentários."
    ),
}

# La traducción parte de un original revisado, pero si ese original trae una
# fórmula prohibida, traducirla al pie de la letra la reintroduce en otro idioma.
_SISTEMA_TRADUCIR = {
    "es": (
        "Sos un traductor profesional. Traducí al español rioplatense (voseo) el párrafo del usuario, "
        "que ya fue revisado: conservá el sentido, el tono y el largo (60 a 90 palabras). "
        + _PROHIBIDAS["es"]
        + "Si el original usa una fórmula prohibida, la traducción la evita con otra construcción. "
        + _REGLA_GENERO["es"]
        + "Devolvé SOLO la traducción, sin título, sin comillas ni comentarios."
    ),
    "en": (
        "You are a professional translator. Translate the user's paragraph into English. It has "
        "already been reviewed: keep the meaning, the warm direct tone and the length (60 to 90 words). "
        + _PROHIBIDAS["en"]
        + "If the original uses a forbidden phrase, the translation avoids it with a different construction. "
        "Return ONLY the translation, with no title, quotation marks or comments."
    ),
    "pt": (
        "Você é um tradutor profissional. Traduza para o português brasileiro o parágrafo do usuário, "
        "que já foi revisado: conserve o sentido, o tom e o tamanho (60 a 90 palavras). "
        + _PROHIBIDAS["pt"]
        + "Se o original usa uma fórmula proibida, a tradução a evita com outra construção. "
        + _REGLA_GENERO["pt"]
        + "Devolva SÓ a tradução, sem título, aspas nem comentários."
    ),
}


def _con_genero(*raices: str) -> tuple[str, ...]:
    """Las dos formas, -o y -a, de cada raíz terminada en -o."""
    return tuple(f for r in raices for f in (r, r[:-1] + "a"))


# Formas que marcan el género de quien lee. El prompt ya lo prohíbe, pero la segunda
# tanda real igual dejó «Mostrarte entero»: la salida se valida con esta lista, y el
# test de la Task 3 sobre los textos revisados usa esta misma. «solo» queda afuera:
# como adverbio («no solo», «solo cuando») daría un falso positivo en casi todo
# párrafo; «sola» sí está. En inglés no hay marca de género.
FORMAS_CON_GENERO: dict[str, tuple[str, ...]] = {
    "es": _con_genero(
        "generoso", "intenso", "apasionado", "cariñoso", "orgulloso", "ambicioso", "inadvertido",
        "quieto", "clavado", "atrapado", "conquistado", "entero",
    ) + ("sola", "seguro de", "segura de", "duro con", "dura con"),
    "en": (),
    "pt": _con_genero(
        "generoso", "intenso", "apaixonado", "carinhoso", "orgulhoso", "ambicioso", "quieto",
        "preso", "conquistado", "inteiro", "despercebido",
    ),
}


def _palabras(texto: str) -> list[str]:
    return re.findall(r"\w+", texto.lower())


def frases_repetidas(textos: dict[str, str], n: int = 3, tope: int = 6) -> list[tuple[str, int]]:
    """N-gramas de `n` palabras presentes en más de `tope` textos distintos.

    Cuenta textos, no apariciones: una frase repetida diez veces en un solo texto
    no es una muletilla del conjunto. Ordena de más a menos frecuente y descarta
    los n-gramas hechos sólo de palabras vacías.
    """
    cuenta: Counter[str] = Counter()
    for texto in textos.values():
        palabras = _palabras(texto)
        vistos = {" ".join(palabras[i:i + n]) for i in range(len(palabras) - n + 1)}
        cuenta.update(g for g in vistos if not all(p in _VACIAS for p in g.split()))
    return sorted(((g, c) for g, c in cuenta.items() if c > tope), key=lambda x: (-x[1], x[0]))


def _muletillas_en(texto: str, lang: str) -> list[str]:
    """Muletillas de `lang` en un texto: por palabra completa; las aperturas, sólo al inicio."""
    t = texto.lower()
    halladas = [m for m in _MULETILLAS_EN_CUERPO[lang] if re.search(rf"\b{re.escape(m)}\b", t)]
    # Sólo al inicio: se saltea la puntuación o comilla de apertura.
    halladas += [m for m in _APERTURAS[lang] if re.match(rf"\W*{re.escape(m)}\b", t)]
    return halladas


def muletillas_presentes(textos: dict[str, str], lang: str) -> dict[str, int]:
    """Cuántos textos contienen cada muletilla de `lang` (sólo las que aparecen)."""
    cuenta: Counter[str] = Counter()
    for texto in textos.values():
        cuenta.update(_muletillas_en(texto, lang))
    return {m: cuenta[m] for m in MULETILLAS[lang] if cuenta[m]}


def _problemas(texto: str, lang: str) -> list[tuple[str, str]]:
    """Pares (tipo, valor): tipo es «muletilla», «género» o «largo»."""
    problemas = [("muletilla", m) for m in _muletillas_en(texto, lang)]
    minusculas = texto.lower()
    problemas += [
        ("género", f) for f in FORMAS_CON_GENERO[lang] if re.search(rf"\b{re.escape(f)}\b", minusculas)
    ]
    palabras = len(texto.split())
    if not PALABRAS_MIN <= palabras <= PALABRAS_MAX:
        problemas.append(("largo", f"{palabras} palabras (se esperan {PALABRAS_MIN}-{PALABRAS_MAX})"))
    return problemas


def problemas_de_texto(texto: str, lang: str) -> list[str]:
    """Lista legible de lo que está mal en un texto del teaser; vacía si está bien."""
    return [f"{tipo}: «{valor}»" if tipo != "largo" else f"largo: {valor}" for tipo, valor in _problemas(texto, lang)]


_EVITA = {"es": "Evitá", "en": "Avoid", "pt": "Evite"}
_LARGO_PEDIDO = {
    "es": "El texto tiene que tener entre 60 y 90 palabras.",
    "en": "The text must be between 60 and 90 words long.",
    "pt": "O texto tem que ter entre 60 e 90 palavras.",
}


def _linea_de_reintento(problemas: list[tuple[str, str]], lang: str) -> str:
    """Línea en el idioma destino que nombra lo concreto a evitar en el nuevo intento."""
    citas = ", ".join(f"\"{v}\"" for t, v in problemas if t != "largo")
    partes = [f"{_EVITA[lang]}: {citas}." if citas else ""]
    if any(t == "largo" for t, _ in problemas):
        partes.append(_LARGO_PEDIDO[lang])
    return " ".join(p for p in partes if p)


def _cargar(ruta: pathlib.Path) -> dict[str, dict[str, str]]:
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = "Genera (o traduce) los textos fijos del teaser para un idioma. Sólo desarrollo."

    def add_arguments(self, parser):
        parser.add_argument("--lang", required=True, choices=IDIOMAS)
        parser.add_argument("--desde", choices=IDIOMAS, help="Traduce los textos revisados de este idioma.")
        parser.add_argument("--forzar", action="store_true", help="Regenera un idioma que ya está en el archivo.")
        parser.add_argument("--salida", default=str(RUTA_DEFAULT), help="JSON a escribir/actualizar.")

    def handle(self, *args, **options):
        lang, desde = options["lang"], options["desde"]
        ruta = pathlib.Path(options["salida"])
        if desde == lang:
            raise CommandError("--desde tiene que ser otro idioma que --lang.")
        datos = _cargar(ruta)
        # El flujo es generar, editar a mano y traducir desde lo revisado: pisar
        # un idioma ya escrito perdería esas ediciones y gasta 72 llamadas.
        if datos.get(lang) and not options["forzar"]:
            raise CommandError(f"«{lang}» ya está en {ruta}; usá --forzar para regenerarlo y perder lo editado.")
        origen = datos.get(desde, {}) if desde else {}
        if desde:
            faltan = [k for k in self._claves() if not origen.get(k)]
            if faltan:
                raise CommandError(f"Faltan {len(faltan)} textos en «{desde}» (p. ej. {faltan[0]}).")

        cliente = _build_client()
        nuevos: dict[str, str] = {}
        reintentados: list[str] = []
        con_problemas: dict[str, list[str]] = {}
        for clave in self._claves():
            cuerpo, signo = clave.split("|")
            if desde:
                system = _SISTEMA_TRADUCIR[lang]
                pedido = origen[clave]
            else:
                nombre = nombre_signo(signo, lang)
                system = _SISTEMA_GENERAR[lang].format(cuerpo=_CUERPO[lang][cuerpo], signo=nombre)
                pedido = f"{_CUERPO[lang][cuerpo]} {_PREPOSICION[lang]} {nombre}"
            texto, intentos, problemas = self._texto_valido(cliente, system, pedido, lang, clave)
            if intentos > 1:
                reintentados.append(clave)
            if problemas:
                con_problemas[clave] = problemas
                self.stderr.write(
                    f"AVISO {lang} {clave}: quedó con problemas tras {intentos} intentos: " + "; ".join(problemas)
                )
            nuevos[clave] = texto

        self.stderr.write(
            f"AVISO {lang}: {len(reintentados)} textos con reintento, {len(con_problemas)} con problemas"
            + (f" ({', '.join(con_problemas)})" if con_problemas else "") + "."
        )
        self._avisar_repeticion(nuevos, lang)
        datos[lang] = nuevos
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(f"{len(nuevos)} textos de «{lang}» escritos en {ruta}. Revisalos a mano.")

    def _texto_valido(self, cliente, system: str, pedido: str, lang: str, clave: str) -> tuple[str, int, list[str]]:
        """Pide el texto y, si `problemas_de_texto` no da vacío, lo vuelve a pedir.

        Hasta `REINTENTOS` veces más, sumando al pedido una línea que nombra lo
        concreto a evitar. Si no hay caso, devuelve el mejor intento (el de menos
        problemas): nunca aborta, el aviso lo da quien llama. Devuelve
        (texto, intentos hechos, problemas que le quedan).
        """
        mejor: tuple[str, list[tuple[str, str]]] | None = None
        mensaje = pedido
        intentos = 0
        for intentos in range(1, REINTENTOS + 2):
            try:
                texto = _stream_text(
                    cliente, MODEL, [{"type": "text", "text": system}], mensaje, MAX_TOKENS,
                    thinking={"type": "disabled"},
                ).strip()
            except InterpretationError as exc:
                logger.error("teaser: falló %s/%s: %s", lang, clave, exc)
                raise CommandError(f"Falló {clave}: {exc}") from exc
            problemas = _problemas(texto, lang)
            if mejor is None or len(problemas) < len(mejor[1]):
                mejor = (texto, problemas)
            if not problemas:
                break
            mensaje = f"{pedido}\n\n{_linea_de_reintento(problemas, lang)}"
        assert mejor is not None
        texto, problemas = mejor
        legibles = [f"{t}: {v}" for t, v in problemas]
        return texto, intentos, legibles

    def _avisar_repeticion(self, textos: dict[str, str], lang: str) -> None:
        """Aviso, no error: la repetición se corrige editando o regenerando a mano."""
        for frase, cuantos in frases_repetidas(textos):
            self.stderr.write(f"AVISO {lang} REPETIDA en {cuantos} textos: «{frase}»")
        for muletilla, cuantos in muletillas_presentes(textos, lang).items():
            self.stderr.write(f"AVISO {lang} MULETILLA prohibida en {cuantos} textos: «{muletilla}»")

    @staticmethod
    def _claves() -> list[str]:
        return [f"{c}|{s}" for c in CUERPOS_TEASER for s in SIGNOS]
