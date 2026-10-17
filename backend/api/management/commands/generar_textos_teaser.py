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

from django.core.management.base import BaseCommand, CommandError

from api.firma_frases import IDIOMAS, SIGNOS, nombre_signo
from api.interpretation_service import _build_client
from interpret.exceptions import InterpretationError
from interpret.generator import _stream_text
from interpret.prompts import MODEL

logger = logging.getLogger(__name__)

# Los cuerpos del teaser. La Task 4 los mueve a `api/teaser.py`.
CUERPOS_TEASER: tuple[str, ...] = ("Sun", "Moon", "Ascendant", "Mercury", "Venus", "Mars")

RUTA_DEFAULT = pathlib.Path(__file__).resolve().parents[2] / "data" / "teaser_textos.json"

MAX_TOKENS = 600
PALABRAS_MIN, PALABRAS_MAX = 50, 110

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

# Un prompt por idioma, escrito en ese idioma, con la regla de género y el
# ejemplo de la voz en ese idioma: con uno solo en español, el inglés y el
# portugués salían con calcos del voseo. En inglés no hay regla de género.
_SISTEMA_GENERAR = {
    "es": (
        "Escribís textos para la vista previa gratuita de una carta natal. Un párrafo de 60 a 90 "
        "palabras, en español rioplatense (voseo), sobre qué significa tener {cuerpo} en {signo}. "
        "Hablale a la persona en segunda persona, con tono cálido y directo, como las frases cortas "
        "de una carta natal («Arrancás antes que nadie: tu identidad se afirma en la acción…»). "
        "Sin promesas ni predicciones: describí tendencias, no lo que va a pasar. "
        "Nunca uses adjetivos, participios ni pronombres con género referidos a la persona que lee "
        "(nada terminado en -o/-a para ella: ni «segura» ni «seguro», ni «vos misma»); reformulá con "
        "verbos, sustantivos o adjetivos que no cambian. Sin barras, «x», «@» ni «e» neutra. "
        "Devolvé SOLO el párrafo, sin título, sin comillas ni comentarios."
    ),
    "en": (
        "You write texts for the free preview of a natal chart. One paragraph of 60 to 90 words, "
        "in English, about what it means to have {cuerpo} in {signo}. Address the reader in the second "
        "person, in a warm, direct tone, like the short lines of a natal chart reading "
        "(\u201cYou start before anyone else: your identity is built on action\u2026\u201d). "
        "No promises and no predictions: describe tendencies, not what will happen. "
        "Return ONLY the paragraph, with no title, quotation marks or comments."
    ),
    "pt": (
        "Você escreve textos para a prévia gratuita de um mapa natal. Um parágrafo de 60 a 90 "
        "palavras, em português brasileiro, sobre o que significa ter {cuerpo} em {signo}. "
        "Fale com a pessoa em segunda pessoa (você), com tom caloroso e direto, como as frases curtas "
        "de um mapa natal («Você começa antes de todo mundo: sua identidade se afirma na ação…»). "
        "Sem promessas nem previsões: descreva tendências, não o que vai acontecer. "
        "Nunca use adjetivos, particípios nem pronomes com gênero referidos a quem lê (nada terminado "
        "em -o/-a para essa pessoa: nem «segura» nem «seguro», nem «você mesma»; nem «o»/«a» como "
        "pronome oblíquo: use «te» ou «lhe»); reformule com verbos, substantivos ou adjetivos que não "
        "mudam. Sem barras, «x», «@» nem «e» neutro. "
        "Devolva SÓ o parágrafo, sem título, aspas nem comentários."
    ),
}

_SISTEMA_TRADUCIR = {
    "es": (
        "Sos un traductor profesional. Traducí al español rioplatense (voseo) el párrafo del usuario, "
        "que ya fue revisado: conservá el sentido, el tono y el largo (60 a 90 palabras). "
        "Nunca uses adjetivos, participios ni pronombres con género referidos a la persona que lee "
        "(ni «segura» ni «seguro», ni «vos misma»); reformulá con verbos, sustantivos o adjetivos "
        "que no cambian. Devolvé SOLO la traducción, sin título, sin comillas ni comentarios."
    ),
    "en": (
        "You are a professional translator. Translate the user's paragraph into English. It has "
        "already been reviewed: keep the meaning, the warm direct tone and the length (60 to 90 words). "
        "Return ONLY the translation, with no title, quotation marks or comments."
    ),
    "pt": (
        "Você é um tradutor profissional. Traduza para o português brasileiro o parágrafo do usuário, "
        "que já foi revisado: conserve o sentido, o tom e o tamanho (60 a 90 palavras). "
        "Nunca use adjetivos, particípios nem pronomes com gênero referidos a quem lê (nem «segura» "
        "nem «seguro», nem «você mesma»; nem «o»/«a» como pronome oblíquo: use «te» ou «lhe»); "
        "reformule com verbos, substantivos ou adjetivos que não mudam. "
        "Devolva SÓ a tradução, sem título, aspas nem comentários."
    ),
}


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
        for clave in self._claves():
            cuerpo, signo = clave.split("|")
            if desde:
                system = _SISTEMA_TRADUCIR[lang]
                pedido = origen[clave]
            else:
                nombre = nombre_signo(signo, lang)
                system = _SISTEMA_GENERAR[lang].format(cuerpo=_CUERPO[lang][cuerpo], signo=nombre)
                pedido = f"{_CUERPO[lang][cuerpo]} {_PREPOSICION[lang]} {nombre}"
            try:
                texto = _stream_text(
                    cliente, MODEL, [{"type": "text", "text": system}], pedido, MAX_TOKENS,
                    thinking={"type": "disabled"},
                ).strip()
            except InterpretationError as exc:
                logger.error("teaser: falló %s/%s: %s", lang, clave, exc)
                raise CommandError(f"Falló {clave}: {exc}") from exc
            palabras = len(texto.split())
            if not PALABRAS_MIN <= palabras <= PALABRAS_MAX:
                self.stderr.write(f"AVISO {lang} {clave}: {palabras} palabras (se esperan {PALABRAS_MIN}-{PALABRAS_MAX}).")
            nuevos[clave] = texto

        datos[lang] = nuevos
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(f"{len(nuevos)} textos de «{lang}» escritos en {ruta}. Revisalos a mano.")

    @staticmethod
    def _claves() -> list[str]:
        return [f"{c}|{s}" for c in CUERPOS_TEASER for s in SIGNOS]
