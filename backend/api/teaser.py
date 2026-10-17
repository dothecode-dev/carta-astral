"""El teaser fijo de la vista previa: párrafos por cuerpo y signo, más el
índice bloqueado del informe pago.

No llama al modelo: los párrafos salen de `data/teaser_textos.json`, revisado a
mano, y el índice se calcula con las MISMAS funciones que reparten los temas en
el informe (`interpret.reparto.temas()` + `interpret.prompts.SECCIONES`), para
que el teaser nunca prometa algo que el informe no trate.
"""

import json
import logging
import pathlib

from api.firma_frases import IDIOMAS, nombre_signo
from interpret.prompts import secciones_natal
from interpret.reparto import ASPECTOS, NOMBRES, ROMANOS, TENSOS, Tema, temas

logger = logging.getLogger(__name__)

# Los cuerpos del teaser, en el orden en que se muestran.
CUERPOS_TEASER: tuple[str, ...] = ("Sun", "Moon", "Ascendant", "Mercury", "Venus", "Mars")

MAX_TEMAS_POR_SECCION = 2
# Salen en casi todas las cartas: no dicen nada de esta persona. Se excluyen de
# lo mostrado, no del informe.
_CONJUNCIONES_COMUNES = (frozenset({"Sun", "Mercury"}), frozenset({"Sun", "Venus"}))

_RUTA = pathlib.Path(__file__).parent / "data" / "teaser_textos.json"
_TEXTOS: dict[str, dict[str, str]] = json.loads(_RUTA.read_text(encoding="utf-8"))

# Cuántos planetas tiene un cúmulo, en letras (el mínimo es 3).
_CANTIDAD = {
    "es": {3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 8: "ocho", 9: "nueve", 10: "diez"},
    "en": {3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"},
    "pt": {3: "três", 4: "quatro", 5: "cinco", 6: "seis", 7: "sete", 8: "oito", 9: "nove", 10: "dez"},
}
_FORMAS = {
    "es": {"en_signo": "{p} en {s}", "en_casa": "{base} en la casa {casa}",
           "cumulo": "{n} planetas en la casa {casa}"},
    "en": {"en_signo": "{p} in {s}", "en_casa": "{base} in the {casa} house",
           "cumulo": "{n} planets in the {casa} house"},
    "pt": {"en_signo": "{p} em {s}", "en_casa": "{base} na casa {casa}",
           "cumulo": "{n} planetas na casa {casa}"},
}
# El segundo cuerpo de un aspecto lleva artículo donde el idioma lo pide:
# «con la Luna», «com o Ascendente». Los planetas con nombre propio, no.
_ARTICULO = {
    "es": {"Sun": "el", "Moon": "la", "Ascendant": "el", "Medium_Coeli": "el"},
    "pt": {"Sun": "o", "Moon": "a", "Ascendant": "o", "Medium_Coeli": "o"},
    "en": {},
}
# «a» + artículo se contrae: «al Sol», «ao Sol», «à Lua».
_CONTRACCION = {("es", "el"): "al", ("pt", "o"): "ao", ("pt", "a"): "à"}


def _casa(casa: str, lang: str) -> str:
    """La casa como se escribe en `lang`: romano en es/pt, ordinal en inglés."""
    if lang != "en":
        return ROMANOS[casa]
    n = list(ROMANOS).index(casa) + 1
    sufijo = "th" if 10 <= n <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{sufijo}"


def _aspecto(t: Tema, lang: str) -> str:
    assert t.aspecto is not None
    n = NOMBRES[lang]
    frase = ASPECTOS[lang][t.aspecto]
    segundo = t.puntos[1]
    art = _ARTICULO[lang].get(segundo)
    if not art:
        return f"{n[t.puntos[0]]} {frase} {n[segundo]}"
    if frase.endswith(" a") and (lang, art) in _CONTRACCION:
        return f"{n[t.puntos[0]]} {frase[:-2]} {_CONTRACCION[(lang, art)]} {n[segundo]}"
    return f"{n[t.puntos[0]]} {frase} {art} {n[segundo]}"


def _signos(data: dict) -> dict[str, str]:
    signos = {p["name"]: p["sign"] for p in data.get("placements") or []}
    if data.get("time_known") and data.get("angles"):
        signos.update({a["name"]: a["sign"] for a in data["angles"]})
    return signos


def _luna_dudosa(data: dict) -> bool:
    return bool((data.get("flags") or {}).get("moon_sign_uncertain"))


def _nombre_tema(t: Tema, lang: str, data: dict) -> str:
    """El tema nombrado para la persona lectora, en `lang`."""
    n, f = NOMBRES[lang], _FORMAS[lang]
    if t.tipo == "planeta":
        punto = t.puntos[0]
        texto = f["en_signo"].format(p=n[punto], s=nombre_signo(_signos(data)[punto], lang))
        casa = next((p.get("house") for p in data.get("placements") or [] if p["name"] == punto), None)
        if data.get("time_known") and casa in ROMANOS:
            texto = f["en_casa"].format(base=texto, casa=_casa(casa, lang))
        return texto
    if t.tipo == "cumulo":
        assert t.casa is not None
        return f["cumulo"].format(n=_CANTIDAD[lang][len(t.puntos)], casa=_casa(t.casa, lang))
    return _aspecto(t, lang)


def _prioridad(t: Tema) -> int:
    if t.tipo == "aspecto":
        return 0 if t.aspecto in TENSOS else 1
    return 2 if t.tipo == "cumulo" else 3


def _mostrable(t: Tema, data: dict) -> bool:
    if t.tipo == "aspecto" and t.aspecto == "conjunction" and frozenset(t.puntos) in _CONJUNCIONES_COMUNES:
        return False
    # Sin hora la Luna puede cambiar de signo en el día: no se nombra.
    if t.tipo == "planeta" and t.puntos[0] == "Moon" and _luna_dudosa(data):
        return False
    return True


def _bloques(data: dict) -> list[dict]:
    signos = _signos(data)
    bloques = []
    for cuerpo in CUERPOS_TEASER:
        if cuerpo not in signos or (cuerpo == "Moon" and _luna_dudosa(data)):
            continue
        signo = signos[cuerpo]
        textos = {lang: _TEXTOS.get(lang, {}).get(f"{cuerpo}|{signo}") for lang in IDIOMAS}
        faltan = [lang for lang, t in textos.items() if not t]
        for lang in faltan:
            logger.warning("teaser: falta texto cuerpo=%s signo=%s lang=%s", cuerpo, signo, lang)
        if faltan:
            continue
        bloques.append({"cuerpo": cuerpo, "signo": signo, "textos": textos})
    return bloques


def _elegidos(data: dict, slug: str) -> list[Tema]:
    """Los temas propios de la sección `slug` que se muestran, en orden."""
    propios = [t for t in temas(data) if t.duena == slug and _mostrable(t, data)]
    # `sorted` es estable: el desempate es el orden de `reparto.temas()`.
    return sorted(propios, key=_prioridad)[:MAX_TEMAS_POR_SECCION]


def _indice(data: dict, aplicables) -> list[dict]:
    return [
        {
            "slug": s.slug,
            "titulos": {lang: s.titulo[lang] for lang in IDIOMAS},
            "temas": [
                {lang: _nombre_tema(t, lang, data) for lang in IDIOMAS}
                for t in _elegidos(data, s.slug)
            ],
        }
        for s in aplicables
    ]


def teaser(data: dict) -> dict:
    """El teaser para el `data` serializado de una carta (forma de RF5)."""
    aplicables = secciones_natal(bool(data.get("time_known")))
    palabras = sum(s.palabras for s in aplicables)
    return {
        "bloques": _bloques(data),
        "indice": _indice(data, aplicables),
        "informe": {"secciones": len(aplicables), "palabras": int(palabras / 1000 + 0.5) * 1000},
    }
