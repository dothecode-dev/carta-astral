"""El PDF de la carta: de la geometría validada al documento.

Este módulo construye el markup, no lo filtra. Es la diferencia que ordena todo
lo demás: el cliente manda números y texto, y acá se arma el SVG y el HTML. Con
texto la defensa es escapar, que es una operación total; con markup ajeno habría
que mantener una lista blanca, que es una operación que un día tiene un agujero.

La estética es la del PDF de la app (`src/share/chartPdf.ts` en el repo de la
app): fondo violeta, dorado, mono para los datos. El documento no sigue el tema
claro/oscuro de quien lo pide: es una pieza de marca y se ve igual siempre.
"""

from __future__ import annotations

import base64
import functools
import html
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import quote

from api import pdf_payload
from api.interpretation_service import DISCLAIMERS
from api.models import Chart
from interpret.prompts import PROMPT_VERSION

logger = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent / "pdf_assets"

PALETTE = {
    "void": "#150715",
    "starlight": "#F9F7F7",
    "stardust": "#A79BAF",
    "sol": "#D5C046",
    "orbit": "rgba(178, 173, 138, 0.28)",
    "orbit_strong": "rgba(178, 173, 138, 0.6)",
    "dotted": "#DCCB54",
    "danger": "#CD1561",
}

# El aire alrededor de la rueda, en unidades del viewBox: los rótulos de los
# ejes se dibujan por fuera del anillo exterior y sin este margen se cortan.
WHEEL_MARGIN = 16

# Los tonos de aspecto, que el cliente nombra y este módulo colorea.
TONE_COLOR = {
    "soft": PALETTE["dotted"],
    "hard": "#CD1561",
    "neutral": PALETTE["orbit_strong"],
}


class PdfGenerationError(RuntimeError):
    """El documento no se pudo escribir."""


@functools.lru_cache(maxsize=1)
def pdf_url_fetcher() -> Any:
    """El generador no sale a buscar nada.

    WeasyPrint resuelve URLs por su cuenta: en el spike del 16-08-2026 intentó
    traer `<img src>`, `<image href>`, `xlink:href` y el `background-image` de un
    atributo `style`, incluido `169.254.169.254` —el endpoint de metadata de
    instancia—. Que el markup lo generemos nosotros no cambia que esto tenga que
    estar: es la segunda llave, independiente de la primera.

    `data:` es la única excepción y no es una concesión: son los bytes de las
    tipografías que embebe este mismo módulo. No hay red del otro lado.

    El import es perezoso a propósito: si algún día la imagen se construye sin
    las libs de Pango, cae este endpoint con un 503 y no el sitio entero.
    """
    from weasyprint import URLFetcher

    class _SoloDatos(URLFetcher):
        def fetch(self, url: str, headers: Any = None) -> Any:
            if not url.startswith("data:"):
                logger.warning("pdf: recurso externo bloqueado: %s", url[:120])
            # `allowed_protocols` hace el rechazo; el log es para enterarnos.
            return super().fetch(url, headers)

    return _SoloDatos(allowed_protocols=("data",))


@functools.lru_cache(maxsize=1)
def _font_css() -> str:
    """Las tipografías de marca, embebidas. Subsets latinos, licencia OFL."""
    fuentes = [
        ("Outfit", 300, "Outfit-Light.woff2"),
        ("Outfit", 400, "Outfit-Regular.woff2"),
        ("Space Mono", 400, "SpaceMono-Regular.woff2"),
    ]
    bloques = []
    for familia, peso, archivo in fuentes:
        datos = base64.b64encode((ASSETS / archivo).read_bytes()).decode("ascii")
        bloques.append(
            f"@font-face {{ font-family: '{familia}'; font-weight: {peso}; "
            f"src: url(data:font/woff2;base64,{datos}) format('woff2'); }}"
        )
    return "\n".join(bloques)


@functools.lru_cache(maxsize=1)
def _base_css() -> str:
    """La hoja de estilos del documento, dinámica sólo en la paleta.

    Los colores de marca son variables CSS que se fijan acá desde `PALETTE`
    —la misma fuente que usa `_svg`—; el resto de las reglas vive en
    `pdf_assets/informe.css` como una hoja de estilos de verdad, no como un
    f-string gigante.
    """
    variables = "\n".join(f"  --{clave.replace('_', '-')}: {valor};" for clave, valor in PALETTE.items())
    hoja = (ASSETS / "informe.css").read_text(encoding="utf-8")
    return f":root {{\n{variables}\n}}\n{hoja}"


def _esc(texto: str) -> str:
    return html.escape(texto, quote=True)


def _svg(wheel: dict) -> str:
    """La rueda, pintada a partir de la geometría que calculó `astra-wheel`.

    Acá no hay trigonometría y no debe haberla: si el backend empezara a calcular
    dónde va un glifo, habría dos geometrías que mantener sincronizadas y la que
    ve la web dejaría de ser la que sale en el PDF.
    """
    size = wheel["view_box"]
    c = wheel["center"]
    r = wheel["rings"]
    p = PALETTE
    partes = [
        f'<circle cx="{c}" cy="{c}" r="{r["outer"]}" stroke="{p["orbit_strong"]}" stroke-width="1.5" fill="none"/>',
        f'<circle cx="{c}" cy="{c}" r="{r["signs"]}" stroke="{p["orbit"]}" stroke-width="1" fill="none"/>',
        f'<circle cx="{c}" cy="{c}" r="{r["houses"]}" stroke="{p["orbit"]}" stroke-width="1" fill="none"/>',
        f'<circle cx="{c}" cy="{c}" r="{r["aspect"]}" stroke="{p["dotted"]}" '
        f'stroke-width="0.8" stroke-dasharray="1.5 4" fill="none"/>',
    ]

    for s in wheel["signs"]:
        partes.append(
            f'<text x="{s["x"]}" y="{s["y"]}" font-size="17" fill="{p["stardust"]}" '
            f'text-anchor="middle">{_esc(s["glyph"])}</text>'
        )

    for cusp in wheel["cusps"]:
        eje = cusp["axis"]
        dash = "" if eje else ' stroke-dasharray="2 3"'
        color = p["orbit_strong"] if eje else p["orbit"]
        partes.append(
            f'<line x1="{cusp["x1"]}" y1="{cusp["y1"]}" x2="{cusp["x2"]}" y2="{cusp["y2"]}" '
            f'stroke="{color}" stroke-width="{1.2 if eje else 0.6}"{dash}/>'
            f'<text x="{cusp["label_x"]}" y="{cusp["label_y"]}" font-size="11" '
            f'fill="{p["stardust"]}" text-anchor="middle">{_esc(cusp["label"])}</text>'
        )

    for linea in wheel["aspect_lines"]:
        partes.append(
            f'<line x1="{linea["x1"]}" y1="{linea["y1"]}" x2="{linea["x2"]}" y2="{linea["y2"]}" '
            f'stroke="{TONE_COLOR[linea["tone"]]}" stroke-width="0.9" opacity="0.8"/>'
        )

    for a in wheel["angles"]:
        partes.append(
            f'<text x="{a["x"]}" y="{a["y"]}" font-size="10" fill="{p["sol"]}" '
            f'text-anchor="middle">{_esc(a["label"])}</text>'
        )

    for b in wheel["bodies"]:
        color = p["sol"] if b["accent"] else p["starlight"]
        partes.append(
            f'<line x1="{b["tick_x1"]}" y1="{b["tick_y1"]}" x2="{b["tick_x2"]}" y2="{b["tick_y2"]}" '
            f'stroke="{p["sol"]}" stroke-width="1"/>'
            f'<line x1="{b["leader_x1"]}" y1="{b["leader_y1"]}" x2="{b["leader_x2"]}" '
            f'y2="{b["leader_y2"]}" stroke="{p["orbit"]}" stroke-width="0.75"/>'
            f'<text x="{b["x"]}" y="{b["y"]}" font-size="19" fill="{color}" '
            f'text-anchor="middle">{_esc(b["glyph"])}</text>'
        )

    # El viewBox se agranda un poco en los cuatro lados: los rótulos de los ejes
    # van por fuera del borde y el de la izquierda quedaba cortado por la mitad
    # —"ASC" salía "SC"—. Se vio en el spike del 16-08-2026; el PDF de la app
    # probablemente tenga lo mismo, porque el código es el que se portó de ahí.
    m = WHEEL_MARGIN
    return (
        f'<svg width="620" height="620" '
        f'viewBox="{-m} {-m} {size + 2 * m} {size + 2 * m}" '
        f'xmlns="http://www.w3.org/2000/svg">{"".join(partes)}</svg>'
    )


def _matrix_html(matrix: dict) -> str:
    """La matriz triangular de aspectos, como la de la web.

    Cada cruce dice qué aspecto hay entre esos dos cuerpos, y el color dice si el
    ángulo tensa o fluye. El triángulo superior queda hueco —sin bordes— porque
    la mitad de arriba repetiría la de abajo.

    El cliente manda sólo las celdas del triángulo; acá se completan las que
    faltan hasta el ancho de la tabla.
    """
    labels = matrix["labels"]
    if not labels or not matrix["rows"]:
        return ""

    # El último rótulo nunca encabeza una columna: no tiene con quién cruzarse
    # más abajo.
    columnas = labels[:-1]
    cabecera = "".join(f'<th class="matrixHead">{_esc(g)}</th>' for g in columnas)

    filas = []
    for i, fila in enumerate(matrix["rows"]):
        celdas = []
        for j in range(len(columnas)):
            if j > i:
                celdas.append('<td class="matrixVoid"></td>')
                continue
            celda = fila["cells"][j] if j < len(fila["cells"]) else None
            if celda is None:
                celdas.append('<td class="matrixCell"></td>')
                continue
            tono = {"soft": "matrixSoft", "hard": "matrixHard"}.get(
                celda["tone"], "matrixNeutral"
            )
            celdas.append(f'<td class="matrixCell {tono}">{_esc(celda["glyph"])}</td>')
        filas.append(
            f'<tr><th class="matrixHead">{_esc(fila["label"])}</th>{"".join(celdas)}</tr>'
        )

    return (
        '<table class="aspectMatrix">'
        f'<tr><td class="matrixVoid"></td>{cabecera}</tr>'
        f'{"".join(filas)}'
        "</table>"
    )


def _seccion_html(texto: str) -> str:
    """Los párrafos de una sección. El markdown que escribe el generador es
    liviano —sólo `**` para negrita, que acá se descarta— y no trae sus
    propios títulos: el título es el del catálogo (`Seccion.titulo`), no algo
    que haya que parsear del texto."""
    return "".join(
        f"<p>{_esc(bloque.strip().replace('**', ''))}</p>"
        for bloque in re.split(r"\n\n+", texto.strip())
        if bloque.strip()
    )


def _reading_html(reading: dict, disclaimer: str, titulo: str) -> str:
    """La lectura: el índice de las secciones aplicables —nombra también las
    que todavía no se escribieron, ver `pdf_payload.build`— y el texto de
    cada una que sí está, con su propio título."""
    indice_html = "".join(f"<li>{_esc(t)}</li>" for t in reading["indice"])
    secciones_html = "".join(
        f'<div class="seccion"><h2>{_esc(seccion["titulo"])}</h2>{_seccion_html(seccion["texto"])}</div>'
        for seccion in reading["secciones"]
    )
    return (
        '<div class="pagebreak"></div>'
        f'<div class="section eyebrow">{_esc(titulo)}</div>'
        f'<ol class="indice">{indice_html}</ol>'
        f'<div class="reading">{secciones_html}</div>'
        f'<p class="disclaimer">{_esc(disclaimer)}</p>'
    )


def _reading_for(chart: Chart, lang: str | None) -> tuple[dict, str] | None:
    """El informe pedido, si está escrito y terminado.

    Una interpretación con `completa=False` no se sirve —mismo criterio que
    `InterpretationView.get`—: un informe a medio generar no tiene por qué
    salir en un PDF como si estuviera terminado.
    """
    if not lang:
        return None
    interp = chart.interpretations.filter(
        lang=lang, prompt_version=PROMPT_VERSION, completa=True
    ).first()
    if interp is None:
        # No es un error: la carta se baja igual, sin la lectura.
        return None
    return pdf_payload.build(chart, interp)["reading"], DISCLAIMERS[interp.lang]


def build_document_html(chart: Chart, data: dict) -> str:
    """El documento entero como HTML. Función pura: es donde se verifica todo."""
    labels = data["labels"]

    filas_posiciones = "".join(
        f'<tr><td class="glyph">{_esc(pos["glyph"])}</td>'
        f'<td>{_esc(pos["name"])}{"<span class=\"rx\"> ℞</span>" if pos["retrograde"] else ""}</td>'
        f'<td class="data">{_esc(pos["position"])}</td>'
        f'<td class="data">{_esc(pos["house"])}</td></tr>'
        for pos in data["positions"]
    )
    filas_aspectos = "".join(
        f'<tr><td class="glyph">{_esc(a["glyph"])}</td>'
        f'<td>{_esc(a["name"])}</td>'
        f'<td class="data">{_esc(a["detail"])}</td><td></td></tr>'
        for a in data["aspects"]
    )

    wheel = data.get("wheel")
    rueda = f'<div class="wheel-big">{_svg(wheel)}</div>' if wheel else ""

    lectura = _reading_for(chart, data.get("reading_lang"))
    bloque_lectura = (
        _reading_html(lectura[0], lectura[1], labels["reading"]) if lectura else ""
    )

    matriz = data.get("aspect_matrix")
    # Con matriz, el documento cierra ahí: la carta ocupa dos hojas —la rueda y
    # después las posiciones con la matriz— y la lectura empieza en la tercera.
    # La lista de orbes existe sólo como respaldo, para la carta que no llega a
    # tener matriz; si se dibujara siempre, partiría la página en dos y correría
    # la lectura media hoja.
    if data["aspects"]:
        cuerpo_aspectos = _matrix_html(matriz) if matriz else f"<table>{filas_aspectos}</table>"
        seccion_aspectos = (
            f'<div class="section eyebrow">{_esc(labels["aspects"])}</div>{cuerpo_aspectos}'
        )
    else:
        seccion_aspectos = ""

    return f"""<meta charset="utf-8">
<style>
{_font_css()}
{_base_css()}
</style>
<div class="cover">
  <div class="brand">ASTRA</div>
  <div class="brand-tag">{_esc(labels["brand_tagline"])}</div>
  <div class="eyebrow" style="margin-top:44px">{_esc(labels["eyebrow"])}</div>
  <h1>{_esc(labels["chart_name"])}</h1>
  <div class="birth">{_esc(labels["birth_line"])}</div>
  {rueda}
</div>
<div class="section eyebrow">{_esc(labels["positions"])}</div>
<table>{filas_posiciones}</table>
{seccion_aspectos}
{bloque_lectura}
<div class="footer"><span class="sol">☉</span> {_esc(labels["made_with"])}</div>
"""


def render_pdf(chart: Chart, data: dict) -> bytes:
    """El documento, en bytes.

    Son unos 300 ms de CPU en el worker. El techo de frecuencia lo pone el
    throttle de la view; el de duración, el `--timeout 60` de gunicorn.
    """
    from weasyprint import HTML

    try:
        return HTML(
            string=build_document_html(chart, data),
            url_fetcher=pdf_url_fetcher(),
        ).write_pdf()
    except Exception as exc:
        logger.error(
            "pdf: no se pudo generar el documento de la carta %s: %s",
            chart.uuid, exc, exc_info=True,
        )
        raise PdfGenerationError(str(exc)) from exc


def pdf_filename(nombre: str) -> tuple[str, str]:
    """Nombre de archivo para el header, en sus dos formas.

    Devuelve (ascii, utf8_percent_encoded): el primero es el respaldo para
    clientes viejos, el segundo el que conserva los acentos —"João" no se
    convierte en "Joao" porque el header no sepa transportarlo—.
    """
    limpio = re.sub(r'[\\/:*?"<>|\r\n]+', " ", nombre).strip()
    limpio = re.sub(r"\s+", " ", limpio) or "carta"
    archivo = f"{limpio}.pdf"
    ascii_ = (
        unicodedata.normalize("NFKD", archivo).encode("ascii", "ignore").decode("ascii")
        or "carta.pdf"
    )
    return ascii_, quote(archivo, safe="")
