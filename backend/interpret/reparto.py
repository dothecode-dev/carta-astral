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

DUENA_CASA = {
    "First_House": "firma", "Second_House": "trabajo", "Third_House": "mente",
    "Fourth_House": "casas", "Fifth_House": "afectos", "Sixth_House": "trabajo",
    "Seventh_House": "afectos", "Eighth_House": "casas", "Ninth_House": "casas",
    "Tenth_House": "trabajo", "Eleventh_House": "casas", "Twelfth_House": "casas",
}
CASAS = tuple(DUENA_CASA)
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
            salida.append(Tema("cumulo", DUENA_CASA[casa], miembros, casa=casa, internos=internos))

    for a in aspectos:
        trio = (a["p1"], a["aspect"], a["p2"])
        if trio in absorbidos:
            continue
        duena = "tensiones" if a["aspect"] in TENSOS else DUENA_PUNTO[_mas_personal(a["p1"], a["p2"])]
        salida.append(Tema("aspecto", duena, (a["p1"], a["p2"]), aspecto=a["aspect"]))
    return salida
