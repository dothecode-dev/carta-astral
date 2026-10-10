"""La plantilla común de los mails de ASTRA.

Una sola maqueta para todos los avisos (decisión del 10-10-2026): cabecera con
el ☉ y la marca, una tarjeta en el ambiente «papel» de la web, un botón y un
pie que dice por qué llega el mail y a dónde escribir. Los textos de cada aviso
viven en `notificaciones.py`; acá sólo hay forma.

**Todo lo que entra se escapa.** El nombre de la carta, los alias y el arranque
del informe vienen de personas y del modelo: ninguno se escribe sin pasar por
`html.escape`. La plantilla es la única que arma HTML, para que haya un solo
lugar donde eso se haga bien.

Por qué tablas y estilos en línea: es lo único que Outlook y Gmail respetan.
Los colores son los de la web en modo papel (`web/app/globals.css`) y la
tipografía de los títulos cae a Georgia donde Fraunces no carga.
"""

import html
from dataclasses import dataclass

CONTACTO = "info@astraguia.com"

_PAPEL = "#efeaf1"
_TARJETA = "#f7f4f8"
_TINTA = "#1b0c1e"
_SUAVE = "#55455f"
_ACENTO = "#5f4408"
_PUNTEADO = "#9a8718"
# El filete de la web (tinta al 16%) ya mezclado con la tarjeta: Outlook de
# escritorio ignora los colores con alfa.
_FILETE = "#d4cfd5"

_SERIF = "Fraunces,Georgia,'Times New Roman',serif"
_SANS = "Helvetica,Arial,sans-serif"
_MONO = "Menlo,'Courier New',monospace"
# Los glifos astronómicos (☉ ☽) en Georgia salen diminutos: una pila de
# fuentes de símbolos los dibuja del tamaño de las letras.
_SIMBOLOS = "'Apple Symbols','Segoe UI Symbol','Noto Sans Symbols',Georgia,serif"

_PIE = {
    "es": f"¿Dudas? Escribinos a {CONTACTO}.",
    "en": f"Questions? Write to us at {CONTACTO}.",
    "pt": f"Dúvidas? Escreva para {CONTACTO}.",
}


@dataclass(frozen=True)
class Signo:
    """Una celda de la franja de signos: «☉ / Sol / Piscis»."""

    glifo: str
    rotulo: str
    valor: str


@dataclass(frozen=True)
class Mail:
    preheader: str
    eyebrow: str
    titulo: str
    detalle: str = ""
    parrafos: tuple[str, ...] = ()
    signos: tuple[Signo, ...] = ()
    cita_rotulo: str = ""
    cita: str = ""
    codigo: str = ""
    boton: str = ""
    url: str = ""
    nota: str = ""
    motivo: str = ""


def _e(valor: str) -> str:
    return html.escape(valor, quote=True)


def _signos(signos: tuple[Signo, ...]) -> str:
    ancho = 100 // len(signos)
    celdas = []
    for i, s in enumerate(signos):
        borde = f"border-left:1px solid {_FILETE};" if i else ""
        celdas.append(
            f'<td width="{ancho}%" style="padding:14px 0;text-align:center;{borde}">'
            f'<div style="font:400 26px/30px {_SERIF if s.glifo.isascii() else _SIMBOLOS};'
            f'color:{_ACENTO}">{_e(s.glifo)}</div>'
            f'<div style="font:600 10px/1.6 {_MONO};letter-spacing:.12em;color:{_SUAVE};'
            f'text-transform:uppercase;margin-top:6px">{_e(s.rotulo)}</div>'
            f'<div style="font:400 16px/1.3 {_SERIF};color:{_TINTA}">{_e(s.valor)}</div></td>'
        )
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="margin:26px 0 24px;border-top:1px solid {_FILETE};border-bottom:1px solid {_FILETE}">'
        f'<tr>{"".join(celdas)}</tr></table>'
    )


def _cuerpo(m: Mail) -> str:
    partes = [
        f'<div style="font:600 11px/1.4 {_MONO};letter-spacing:.14em;text-transform:uppercase;'
        f'color:{_ACENTO}">{_e(m.eyebrow)}</div>',
        f'<h1 style="margin:10px 0 6px;font:400 28px/1.25 {_SERIF};color:{_TINTA}">{_e(m.titulo)}</h1>',
    ]
    if m.detalle:
        partes.append(f'<div style="font:400 14px/1.5 {_SANS};color:{_SUAVE}">{_e(m.detalle)}</div>')
    if m.signos:
        partes.append(_signos(m.signos))
    elif m.parrafos or m.codigo or m.cita:
        partes.append('<div style="height:14px;line-height:14px">&nbsp;</div>')
    if m.cita:
        partes.append(
            f'<div style="font:600 11px/1.4 {_MONO};letter-spacing:.14em;text-transform:uppercase;'
            f'color:{_SUAVE};margin-bottom:10px">{_e(m.cita_rotulo)}</div>'
            f'<p style="margin:0 0 28px;font:italic 400 17px/1.65 {_SERIF};color:{_TINTA};'
            f'border-left:2px solid {_PUNTEADO};padding-left:16px">{_e(m.cita)}</p>'
        )
    for parrafo in m.parrafos:
        partes.append(
            f'<p style="margin:0 0 16px;font:400 16px/1.6 {_SANS};color:{_TINTA}">{_e(parrafo)}</p>'
        )
    if m.codigo:
        partes.append(
            f'<div style="display:inline-block;margin:6px 0 8px;padding:16px 28px;'
            f'border:1px dashed {_PUNTEADO};border-radius:12px;background:{_PAPEL};'
            f'font:600 34px/1 {_MONO};letter-spacing:.3em;color:{_TINTA}">{_e(m.codigo)}</div>'
        )
    if m.boton and m.url:
        partes.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" border="0" '
            f'style="margin-top:8px"><tr><td style="border-radius:999px;background:{_TINTA}">'
            f'<a href="{_e(m.url)}" style="display:inline-block;padding:14px 30px;'
            f'font:600 15px/1 {_SANS};color:{_PAPEL};text-decoration:none;border-radius:999px">'
            f'{_e(m.boton)}&nbsp;→</a></td></tr></table>'
        )
    if m.nota:
        partes.append(f'<p style="margin:18px 0 0;font:400 13px/1.6 {_SANS};color:{_SUAVE}">{_e(m.nota)}</p>')
    return "".join(partes)


def render_html(m: Mail, lang: str, logo_url: str) -> str:
    pie = _PIE.get(lang, _PIE["es"])
    motivo = f"{_e(m.motivo)}<br>" if m.motivo else ""
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_e(m.titulo)}</title></head>'
        f'<body style="margin:0;padding:0;background:{_PAPEL}">'
        # Lo que muestra la bandeja al lado del asunto. Oculto en el cuerpo.
        '<div style="display:none;max-height:0;overflow:hidden;opacity:0;mso-hide:all">'
        f'{_e(m.preheader)}</div>'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{_PAPEL}"><tr><td align="center" style="padding:32px 16px">'
        '<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
        'style="max-width:600px;width:100%">'
        '<tr><td style="padding:0 8px 24px">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td><img src="{_e(logo_url)}" width="32" height="32" alt="" '
        'style="display:block;border-radius:7px"></td>'
        f'<td style="padding-left:10px;font:600 15px/1 {_SERIF};letter-spacing:.32em;'
        f'color:{_TINTA}">ASTRA</td></tr></table></td></tr>'
        f'<tr><td style="background:{_TARJETA};border:1px solid {_FILETE};border-radius:14px;'
        f'padding:40px">{_cuerpo(m)}</td></tr>'
        f'<tr><td style="padding:22px 8px 0;font:400 12px/1.6 {_SANS};color:{_SUAVE}">'
        f'{motivo}{_e(pie)}<br>ASTRA · {CONTACTO}</td></tr>'
        '</table></td></tr></table></body></html>'
    )


def render_texto(m: Mail, lang: str) -> str:
    """La versión en texto plano: la que leen los clientes sin HTML y la que
    pesa a favor de que el mail no caiga en spam."""
    lineas = ["ASTRA", "", m.eyebrow.upper(), m.titulo]
    if m.detalle:
        lineas.append(m.detalle)
    if m.signos:
        lineas += ["", " · ".join(f"{s.rotulo}: {s.valor}" for s in m.signos)]
    if m.cita:
        lineas += ["", f"{m.cita_rotulo}:", m.cita]
    for parrafo in m.parrafos:
        lineas += ["", parrafo]
    if m.codigo:
        lineas += ["", m.codigo]
    if m.boton and m.url:
        lineas += ["", f"{m.boton}: {m.url}"]
    if m.nota:
        lineas += ["", m.nota]
    lineas += ["", "--"]
    if m.motivo:
        lineas.append(m.motivo)
    lineas += [_PIE.get(lang, _PIE["es"]), f"ASTRA · {CONTACTO}"]
    return "\n".join(lineas) + "\n"
