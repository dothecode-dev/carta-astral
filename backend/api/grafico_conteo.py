"""El gráfico de líneas del conteo diario, dibujado como SVG en el servidor.

SVG y no una librería de JavaScript: el panel no carga nada de afuera, y así
no depende de una CDN ni choca con una política de seguridad de contenido.
Todo lo que se interpola son números y fechas que arma `conteo.serie`.
"""

from html import escape

ANCHO, ALTO = 900, 220
IZQ, DER, ARRIBA, ABAJO = 44, 16, 36, 30

SERIES = (
    ("carta_calculada", "Cartas calculadas", "#4f8cff"),
    ("checkout_abierto", "Pagos abiertos", "#f5a623"),
    ("compra_pagada", "Compras pagas", "#3fb950"),
)


PALETA = ("#4f8cff", "#f5a623", "#3fb950", "#d16ba5", "#8b949e")


def svg_lineas(serie: dict, claves: tuple[str, ...] | None = None) -> str:
    """Un gráfico con las series de `claves` (todas si no se pasa), con el eje
    Y escalado a ellas: los pagos, de a uno, no pueden compartir escala con
    las cartas, de a decenas, o quedan aplastados contra el piso."""
    return svg_series(serie["fechas"], [
        (nombre, color, serie[clave]) for clave, nombre, color in SERIES
        if claves is None or clave in claves
    ])


def svg_series(fechas: list[str], series: list[tuple[str, str, list[int]]], titulo: str = "") -> str:
    """El gráfico de líneas de `series` (nombre, color, valores por fecha)."""
    n = len(fechas)
    maximo = max([1, *(v for _, _, valores in series for v in valores)])
    alto_util = ALTO - ARRIBA - ABAJO
    ancho_util = ANCHO - IZQ - DER

    def x(i: int) -> float:
        return IZQ + (ancho_util * i / (n - 1) if n > 1 else ancho_util / 2)

    def y(v: int) -> float:
        return ARRIBA + alto_util * (1 - v / maximo)

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ANCHO} {ALTO}" '
        f'width="100%" role="img" aria-label="Conteo diario" '
        f'style="max-width:{ANCHO}px;font:12px system-ui,sans-serif;color:inherit">',
    ]
    if titulo:
        partes.append(f'<title>{escape(titulo)}</title>')
    # Eje Y: 0, la mitad y el máximo, con líneas guía.
    for v in sorted({0, maximo // 2, maximo}):
        partes.append(
            f'<line x1="{IZQ}" x2="{ANCHO - DER}" y1="{y(v):.1f}" y2="{y(v):.1f}" '
            f'stroke="currentColor" stroke-opacity="0.15"/>'
            f'<text x="{IZQ - 6}" y="{y(v) + 4:.1f}" text-anchor="end" fill="currentColor">{v}</text>'
        )
    # Eje X: primera, del medio y última fecha (dd-mm).
    for i in sorted({0, n // 2, n - 1}):
        dia = escape(fechas[i][8:10] + "-" + fechas[i][5:7])
        partes.append(
            f'<text x="{x(i):.1f}" y="{ALTO - 8}" text-anchor="middle" fill="currentColor">{dia}</text>'
        )
    # Una línea por serie, con un punto por día (un solo día no dibuja línea).
    for desplazamiento, (nombre, color, valores) in enumerate(series):
        puntos = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(valores))
        partes.append(
            f'<polyline points="{puntos}" fill="none" stroke="{color}" stroke-width="2"/>'
        )
        partes.extend(
            f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="2.5" fill="{color}"/>'
            for i, v in enumerate(valores)
        )
        lx = IZQ + desplazamiento * 165
        partes.append(
            f'<rect x="{lx}" y="10" width="12" height="12" fill="{color}"/>'
            f'<text x="{lx + 18}" y="20" fill="currentColor">{escape(nombre)}</text>'
        )
    partes.append("</svg>")
    return "".join(partes)
