"""Sinastría: cómo se miran dos cartas.

Es geometría sobre dos `ChartData` que ya calculó `build_chart`, no un cálculo
de efemérides nuevo. Eso es a propósito: las posiciones de una persona son
idénticas en su carta natal y en cualquier vínculo en el que aparezca (RF4 de
la spec de Vínculo), porque salen del mismo lugar. La API de sinastría de
kerykeion haría la misma cuenta con otros sujetos y otra tabla de orbes.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import ChartData

ASPECTOS: dict[str, float] = {
    "conjunction": 0.0, "sextile": 60.0, "square": 90.0, "trine": 120.0, "opposition": 180.0,
}

#: Tabla propia y fija. No se compara contra la de otro sitio: cada uno usa la
#: suya, y lo que se valida afuera son posiciones y ángulos (RF1).
ORBES: dict[str, float] = {
    "conjunction": 8.0, "opposition": 8.0, "trine": 7.0, "square": 7.0, "sextile": 5.0,
}

PUNTOS: tuple[str, ...] = (
    "Sun", "Moon", "Mercury", "Venus", "Mars",
    "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto",
)
ANGULOS: tuple[str, ...] = ("Ascendant", "Medium_Coeli")


@dataclass(frozen=True)
class AspectoCruzado:
    p_a: str
    p_b: str
    aspecto: str
    #: La separación real entre los dos puntos, de 0 a 180.
    angulo: float
    orbe: float


def _puntos(carta: ChartData) -> dict[str, float]:
    puntos = {p.name: p.abs_pos for p in carta.placements if p.name in PUNTOS}
    if carta.time_known and carta.angles:
        puntos.update({g.name: g.abs_pos for g in carta.angles if g.name in ANGULOS})
    return puntos


def separacion(lon_a: float, lon_b: float) -> float:
    d = abs(lon_a - lon_b) % 360.0
    return 360.0 - d if d > 180.0 else d


def aspectos_cruzados(a: ChartData, b: ChartData) -> list[AspectoCruzado]:
    """Cada punto de A contra cada punto de B, dentro de orbe."""
    encontrados = []
    for p_a, lon_a in _puntos(a).items():
        for p_b, lon_b in _puntos(b).items():
            angulo = separacion(lon_a, lon_b)
            for nombre, exacto in ASPECTOS.items():
                orbe = abs(angulo - exacto)
                if orbe <= ORBES[nombre]:
                    encontrados.append(AspectoCruzado(p_a, p_b, nombre, angulo, orbe))
                    break
    return sorted(encontrados, key=lambda x: x.orbe)
