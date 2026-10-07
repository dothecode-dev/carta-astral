"""Qué sección del informe largo explica cada tema de la carta.

El informe se repetía (07-10-2026): cada sección sólo veía los primeros 400
caracteres de las anteriores y los focos del catálogo se pisaban, así que la
misma oposición se explicaba desde cero en cuatro secciones. Acá cada tema
—un planeta en su signo y casa, un cúmulo, un aspecto mayor— tiene UNA
sección dueña que lo explica; las demás lo usan desde su propio tema sin
volver a explicarlo. Spec: docs/2026-10-07-spec-informe-sin-repeticiones.md.

Puro: no importa Django ni `api` (contrato de lint-imports).
"""

from dataclasses import dataclass

PLANETAS = ("Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto")
ANGULOS = ("Ascendant", "Medium_Coeli")
PUNTOS = PLANETAS + ANGULOS
# Un aspecto sin ninguno de éstos es generacional: lo cubre el foco de «lentos».
PERSONALES = ("Sun", "Moon", "Ascendant", "Mercury", "Venus", "Mars", "Medium_Coeli")
MAYORES = ("conjunction", "opposition", "square", "trine", "sextile")
TENSOS = ("opposition", "square")
ORBE_LUMINARES = 6.0
ORBE = 5.0
MINIMO_CUMULO = 3

DUENA_PUNTO = {
    "Sun": "firma", "Moon": "firma", "Ascendant": "firma",
    "Mercury": "mente",
    "Venus": "afectos",
    "Mars": "trabajo", "Saturn": "trabajo", "Medium_Coeli": "trabajo",
    "Jupiter": "lentos", "Uranus": "lentos", "Neptune": "lentos", "Pluto": "lentos",
}

CASAS = (
    "First_House", "Second_House", "Third_House", "Fourth_House", "Fifth_House", "Sixth_House",
    "Seventh_House", "Eighth_House", "Ninth_House", "Tenth_House", "Eleventh_House", "Twelfth_House",
)
# Todo cúmulo es de «casas», cuyo foco es la acumulación. Se probó repartirlos por
# el tema de la casa (la X a «trabajo») y en staging «casas» lo describía igual
# (07-10-2026): el foco de una sección pesa más que el reparto.
DUENA_CUMULO = "casas"
# El ángulo que abre una casa forma parte de su cúmulo.
ANGULO_DE_CASA = {"First_House": "Ascendant", "Tenth_House": "Medium_Coeli"}


@dataclass(frozen=True)
class Tema:
    tipo: str  # "planeta" | "cumulo" | "aspecto"
    duena: str
    puntos: tuple[str, ...]
    aspecto: str | None = None
    casa: str | None = None
    internos: tuple[tuple[str, str, str], ...] = ()

    @property
    def clave(self) -> str:
        if self.tipo == "planeta":
            return f"planeta:{self.puntos[0]}"
        if self.tipo == "cumulo":
            return f"cumulo:{self.casa}"
        return f"aspecto:{self.puntos[0]}|{self.aspecto}|{self.puntos[1]}"


def _califica(a: dict) -> bool:
    p1, p2 = a.get("p1"), a.get("p2")
    if a.get("aspect") not in MAYORES or p1 not in PUNTOS or p2 not in PUNTOS:
        return False
    if p1 not in PERSONALES and p2 not in PERSONALES:
        return False
    tope = ORBE_LUMINARES if {"Sun", "Moon"} & {p1, p2} else ORBE
    return float(a.get("orbit", 99)) <= tope


def _mas_personal(p1: str, p2: str) -> str:
    return min((p1, p2), key=lambda p: PERSONALES.index(p) if p in PERSONALES else len(PERSONALES))


def temas(chart_data: dict) -> list[Tema]:
    """Todos los temas de la carta con su dueña, en orden determinista:
    planetas y ángulos (orden de PUNTOS), cúmulos (orden de casas), aspectos
    sueltos (orden de PUNTOS del par y tipo)."""
    hora = bool(chart_data.get("time_known"))
    placements = [p for p in chart_data.get("placements") or [] if p.get("name") in PLANETAS]
    angulos = {g["name"] for g in (chart_data.get("angles") or [])} if hora else set()

    salida: list[Tema] = []
    presentes = {p["name"] for p in placements} | (angulos & set(ANGULOS))
    for punto in PUNTOS:
        if punto in presentes:
            salida.append(Tema("planeta", DUENA_PUNTO[punto], (punto,)))

    # Sin hora no hay ángulos ni casas: los aspectos que los nombran no existen.
    aspectos = sorted(
        (a for a in chart_data.get("aspects") or [] if _califica(a)),
        key=lambda a: (PUNTOS.index(a["p1"]), PUNTOS.index(a["p2"]), MAYORES.index(a["aspect"])),
    )

    absorbidos: set[tuple[str, str, str]] = set()
    if hora:
        for casa in CASAS:
            miembros = tuple(p for p in PLANETAS if any(
                x["name"] == p and x.get("house") == casa for x in placements
            ))
            if len(miembros) < MINIMO_CUMULO:
                continue
            del_cumulo = set(miembros) | ({ANGULO_DE_CASA[casa]} if casa in ANGULO_DE_CASA else set())
            internos = tuple(
                (a["p1"], a["aspect"], a["p2"]) for a in aspectos
                if a["p1"] in del_cumulo and a["p2"] in del_cumulo
                and (a["p1"] in miembros or a["p2"] in miembros)
            )
            absorbidos |= set(internos)
            salida.append(Tema("cumulo", DUENA_CUMULO, miembros, casa=casa, internos=internos))

    for a in aspectos:
        trio = (a["p1"], a["aspect"], a["p2"])
        if trio in absorbidos:
            continue
        duena = "tensiones" if a["aspect"] in TENSOS else DUENA_PUNTO[_mas_personal(a["p1"], a["p2"])]
        salida.append(Tema("aspecto", duena, (a["p1"], a["p2"]), aspecto=a["aspect"]))
    return salida


@dataclass(frozen=True)
class Parte:
    propios: tuple[Tema, ...]
    # El bool es True si la dueña va ANTES en el informe («como viste en…»).
    ajenos: tuple[tuple[Tema, bool], ...]


def parte_de(chart_data: dict, slug: str, slugs: list[str]) -> Parte:
    """Lo que `slug` explica y lo que sólo usa. `slugs` son las secciones
    aplicables en orden; un tema cuya dueña no aplica se descarta."""
    lista = [t for t in temas(chart_data) if t.duena in slugs]
    if slug == "sintesis":
        return Parte(propios=(), ajenos=tuple((t, True) for t in lista))
    yo = slugs.index(slug)
    propios = tuple(t for t in lista if t.duena == slug)
    ajenos = tuple((t, slugs.index(t.duena) < yo) for t in lista if t.duena != slug)
    return Parte(propios=propios, ajenos=ajenos)


NOMBRES = {
    "es": {"Sun": "Sol", "Moon": "Luna", "Mercury": "Mercurio", "Venus": "Venus", "Mars": "Marte",
           "Jupiter": "Júpiter", "Saturn": "Saturno", "Uranus": "Urano", "Neptune": "Neptuno",
           "Pluto": "Plutón", "Ascendant": "Ascendente", "Medium_Coeli": "Medio Cielo"},
    "en": {"Sun": "Sun", "Moon": "Moon", "Mercury": "Mercury", "Venus": "Venus", "Mars": "Mars",
           "Jupiter": "Jupiter", "Saturn": "Saturn", "Uranus": "Uranus", "Neptune": "Neptune",
           "Pluto": "Pluto", "Ascendant": "Ascendant", "Medium_Coeli": "Midheaven"},
    "pt": {"Sun": "Sol", "Moon": "Lua", "Mercury": "Mercúrio", "Venus": "Vênus", "Mars": "Marte",
           "Jupiter": "Júpiter", "Saturn": "Saturno", "Uranus": "Urano", "Neptune": "Netuno",
           "Pluto": "Plutão", "Ascendant": "Ascendente", "Medium_Coeli": "Meio do Céu"},
}
ASPECTOS = {
    "es": {"conjunction": "en conjunción con", "opposition": "en oposición a", "square": "en cuadratura con",
           "trine": "en trígono con", "sextile": "en sextil con"},
    "en": {"conjunction": "conjunct", "opposition": "opposite", "square": "square",
           "trine": "trine", "sextile": "sextile"},
    "pt": {"conjunction": "em conjunção com", "opposition": "em oposição a", "square": "em quadratura com",
           "trine": "em trígono com", "sextile": "em sextil com"},
}
ROMANOS = dict(zip(CASAS, ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII"), strict=True))
TEXTOS = {
    "es": {
        "planeta": "{p}: su signo y su casa",
        "cumulo": "el cúmulo en la casa {casa} ({miembros})",
        "propios": "TE TOCA EXPLICAR (sólo esta sección los explica a fondo):",
        "ajenos": "LOS EXPLICA OTRA SECCIÓN: usalos desde tu tema en una o dos frases, "
                  "sin volver a explicar qué son ni cómo funcionan:",
        "antes": "como viste en «{t}»", "despues": "lo vas a ver en «{t}»",
    },
    "en": {
        "planeta": "{p}: its sign and house",
        "cumulo": "the cluster in house {casa} ({miembros})",
        "propios": "YOU EXPLAIN (only this section explains these in depth):",
        "ajenos": "ANOTHER SECTION EXPLAINS THESE: use them from your own angle in one or two "
                  "sentences, without explaining again what they are or how they work:",
        "antes": "as you saw in «{t}»", "despues": "you'll see it in «{t}»",
    },
    "pt": {
        "planeta": "{p}: seu signo e sua casa",
        "cumulo": "o acúmulo na casa {casa} ({miembros})",
        "propios": "VOCÊ EXPLICA (só esta seção explica estes a fundo):",
        "ajenos": "OUTRA SEÇÃO EXPLICA ESTES: use-os a partir do seu tema em uma ou duas frases, "
                  "sem explicar de novo o que são nem como funcionam:",
        "antes": "como viu em «{t}»", "despues": "vai ver em «{t}»",
    },
}


def _nombre(t: Tema, lang: str) -> str:
    n = NOMBRES[lang]
    if t.tipo == "planeta":
        return TEXTOS[lang]["planeta"].format(p=n[t.puntos[0]])
    if t.tipo == "cumulo":
        assert t.casa is not None
        return TEXTOS[lang]["cumulo"].format(casa=ROMANOS[t.casa], miembros=", ".join(n[p] for p in t.puntos))
    assert t.aspecto is not None
    return f"{n[t.puntos[0]]} {ASPECTOS[lang][t.aspecto]} {n[t.puntos[1]]}"


def bloque(parte: Parte, lang: str, titulos: dict[str, str]) -> str:
    """El texto que se agrega al pedido de una sección: qué explica y qué sólo
    usa. Vacío si no hay nada que decir."""
    if not parte.propios and not parte.ajenos:
        return ""
    tx = TEXTOS[lang]
    lineas: list[str] = []
    if parte.propios:
        lineas.append(tx["propios"])
        lineas += [f"- {_nombre(t, lang)}" for t in parte.propios]
    if parte.ajenos:
        if lineas:
            lineas.append("")
        lineas.append(tx["ajenos"])
        for t, antes in parte.ajenos:
            donde = tx["antes" if antes else "despues"].format(t=titulos.get(t.duena, t.duena))
            lineas.append(f"- {_nombre(t, lang)} — {donde}")
    return "\n".join(lineas)
