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
from interpret.prompts import SECCIONES
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
    "es": {"en_signo": "{p} en {s}", "en_casa": "{base} en casa {casa}",
           "cumulo": "{n} planetas en la casa {casa}"},
    "en": {"en_signo": "{p} in {s}", "en_casa": "{base} in house {casa}",
           "cumulo": "{n} planets in house {casa}"},
    "pt": {"en_signo": "{p} em {s}", "en_casa": "{base} na casa {casa}",
           "cumulo": "{n} planetas na casa {casa}"},
}


def _secciones_aplicables(hora: bool):
    # Misma regla que `informe_service.secciones_aplicables` (largo): el
    # informe completo menos lo que depende de una hora que no está. Allá
    # recibe un sujeto y acá sólo tenemos el `data`, por eso se replica.
    return [s for s in SECCIONES if hora or not s.requiere_hora]


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
            texto = f["en_casa"].format(base=texto, casa=ROMANOS[casa])
        return texto
    if t.tipo == "cumulo":
        assert t.casa is not None
        return f["cumulo"].format(n=_CANTIDAD[lang][len(t.puntos)], casa=ROMANOS[t.casa])
    assert t.aspecto is not None
    return f"{n[t.puntos[0]]} {ASPECTOS[lang][t.aspecto]} {n[t.puntos[1]]}"


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


def _indice(data: dict, aplicables) -> list[dict]:
    todos = temas(data)
    indice = []
    for s in aplicables:
        propios = [t for t in todos if t.duena == s.slug and _mostrable(t, data)]
        # `sorted` es estable: el desempate es el orden de `reparto.temas()`.
        elegidos = sorted(propios, key=_prioridad)[:MAX_TEMAS_POR_SECCION]
        indice.append({
            "slug": s.slug,
            "titulos": {lang: s.titulo[lang] for lang in IDIOMAS},
            "temas": [{lang: _nombre_tema(t, lang, data) for lang in IDIOMAS} for t in elegidos],
        })
    return indice


def teaser(data: dict) -> dict:
    """El teaser para el `data` serializado de una carta (forma de RF5)."""
    aplicables = _secciones_aplicables(bool(data.get("time_known")))
    palabras = sum(s.palabras for s in aplicables)
    return {
        "bloques": _bloques(data),
        "indice": _indice(data, aplicables),
        "informe": {"secciones": len(aplicables), "palabras": int(palabras / 1000 + 0.5) * 1000},
    }
