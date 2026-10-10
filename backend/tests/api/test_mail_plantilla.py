"""La plantilla común de los mails (`api/mail_plantilla.py`).

Lo que fijan: que lo que viene de datos —nombre de la carta, alias, arranque
del informe, URL— nunca llega sin escapar, que hay versión en texto plano y
que la franja de signos se adapta a cuántos hay (sin hora no hay Ascendente).
"""

import re

import pytest

from api.mail_plantilla import CONTACTO, Mail, Signo, render_html, render_texto

LOGO = "https://astraguia.com/apple-icon.png"
MALICIOSO = '<script>alert(1)</script><img src=x onerror="alert(2)">'


def _mail(**extra):
    base = dict(preheader="pre", eyebrow="Aviso", titulo="Hola")
    return Mail(**{**base, **extra})


@pytest.mark.parametrize("campo", ["titulo", "detalle", "cita", "nota", "motivo", "eyebrow", "preheader"])
def test_todo_texto_de_datos_se_escapa(campo):
    extra = {campo: MALICIOSO, "cita_rotulo": "Así empieza"} if campo == "cita" else {campo: MALICIOSO}
    html = render_html(_mail(**extra), "es", LOGO)
    assert "<script" not in html and "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_parrafos_codigo_y_signos_se_escapan():
    m = _mail(
        parrafos=(MALICIOSO,), codigo=MALICIOSO,
        signos=(Signo("☉", "Sol", MALICIOSO), Signo(MALICIOSO, "Luna", "Leo")),
    )
    html = render_html(m, "es", LOGO)
    assert "<script" not in html and "<img src=x" not in html


def test_una_url_con_comillas_no_rompe_el_href():
    html = render_html(_mail(boton="Ir", url='https://x.example/"onmouseover="alert(1)'), "es", LOGO)
    assert 'href="https://x.example/&quot;onmouseover=&quot;alert(1)"' in html
    assert '" onmouseover=' not in html


def test_el_boton_lleva_el_href_exacto():
    html = render_html(_mail(boton="Ver mi cuenta", url="https://astraguia.com/es/cuenta"), "es", LOGO)
    assert 'href="https://astraguia.com/es/cuenta"' in html and "Ver mi cuenta" in html


def test_sin_url_no_hay_boton():
    assert "<a " not in render_html(_mail(boton="Ver"), "es", LOGO)


@pytest.mark.parametrize("n,ancho", [(3, "33%"), (2, "50%")])
def test_la_franja_se_reparte_entre_los_signos_que_hay(n, ancho):
    signos = tuple(Signo("☉", f"R{i}", f"V{i}") for i in range(n))
    html = render_html(_mail(signos=signos), "es", LOGO)
    assert html.count(f'width="{ancho}"') == n


def test_el_preheader_va_oculto():
    html = render_html(_mail(preheader="Así empieza tu lectura"), "es", LOGO)
    assert re.search(r'display:none[^>]*>Así empieza tu lectura<', html)


@pytest.mark.parametrize("lang,frase", [("es", "Escribinos"), ("en", "Write to us"), ("pt", "Escreva")])
def test_el_pie_dice_a_donde_escribir_en_cada_idioma(lang, frase):
    html = render_html(_mail(), lang, LOGO)
    assert frase in html and CONTACTO in html


def test_un_idioma_que_no_existe_cae_en_espanol():
    assert render_html(_mail(), "de", LOGO) == render_html(_mail(), "es", LOGO)
    assert render_texto(_mail(), "de") == render_texto(_mail(), "es")


def test_el_texto_plano_no_tiene_html_y_trae_el_enlace():
    m = _mail(
        titulo="Tu informe está listo, Ana", detalle="14 de marzo de 1985 · Rosario",
        signos=(Signo("☉", "Sol", "Piscis"), Signo("☽", "Luna", "Leo")),
        cita_rotulo="Así empieza", cita="Hay en tu carta una tensión…",
        boton="Seguir leyendo", url="https://astraguia.com/es/carta/x",
        nota="Ahí mismo también podés bajarlo en PDF.", motivo="Te escribimos porque…",
    )
    texto = render_texto(m, "es")
    assert "<" not in texto and ">" not in texto
    for esperado in ("Sol: Piscis", "Luna: Leo", "Hay en tu carta", "Seguir leyendo: https://astraguia.com/es/carta/x"):
        assert esperado in texto


def test_una_cita_sin_signos_ni_parrafos_no_queda_pegada_al_titulo():
    html = render_html(_mail(cita_rotulo="Así empieza", cita="Algo"), "es", LOGO)
    assert html.index("height:14px") < html.index("Así empieza")
