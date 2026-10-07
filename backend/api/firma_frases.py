"""Las frases fijas de la firma de una carta: Sol, Luna y Ascendente en palabras.

Es lo primero que una persona que no sabe leer glifos puede entender de su
carta, y es contenido revisado a mano, no texto generado por visita: va en la
vista previa pública y no puede costar una llamada al modelo.
"""

import json
import pathlib

CUERPOS: tuple[str, ...] = ("Sun", "Moon", "Ascendant")
# Las abreviaturas de kerykeion, en el orden del zodíaco.
SIGNOS: tuple[str, ...] = ("Ari", "Tau", "Gem", "Can", "Leo", "Vir", "Lib", "Sco", "Sag", "Cap", "Aqu", "Pis")
IDIOMAS: tuple[str, ...] = ("es", "en", "pt")

_RUTA = pathlib.Path(__file__).parent / "data" / "firma_frases.json"
_FRASES: dict[str, dict[str, str]] = json.loads(_RUTA.read_text(encoding="utf-8"))


def frase(cuerpo: str, signo: str, lang: str) -> str:
    return _FRASES[lang][f"{cuerpo}|{signo}"]


def firma(data: dict) -> list[dict]:
    """Las líneas de la firma para el `data` serializado de una carta.

    Sin hora de nacimiento no hay Ascendente (`angles` es None) y la firma
    tiene dos líneas. Toma el `data` ya serializado y no el `ChartData` para
    servir igual a una carta guardada (`Chart.data`) y a una vista previa.
    """
    signos = {p["name"]: p["sign"] for p in data["placements"]}
    if data.get("time_known") and data.get("angles"):
        signos.update({a["name"]: a["sign"] for a in data["angles"]})
    return [
        {
            "cuerpo": cuerpo,
            "signo": signos[cuerpo],
            "frases": {lang: frase(cuerpo, signos[cuerpo], lang) for lang in IDIOMAS},
        }
        for cuerpo in CUERPOS
        if cuerpo in signos
    ]
