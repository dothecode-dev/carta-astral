"""El mail de «tu informe está listo» con la carta adentro (decisión del
10-10-2026): nombre, Sol/Luna/Ascendente y el arranque del informe.

El mail es lo que más se abre del producto y antes era una línea y un link.
Lo que estos tests cuidan es que lo que se suma —datos de la persona y texto
del modelo— salga escapado, que un nombre raro no ensucie el asunto y que una
falla al armar el enriquecimiento nunca deje a alguien sin su aviso.
"""

import datetime

import pytest

from api import informe_service
from api.models import Interpretation, InterpretationSection
from api.vinculo_service import crear_vinculo
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

ARRANQUE = (
    "Hay en tu carta una tensión que no es un defecto sino un motor: un Sol en Piscis que "
    "necesita disolverse en lo que siente y una Luna en Leo que pide ser vista."
)
DATA = {
    "time_known": True,
    "placements": [{"name": "Sun", "sign": "Pis"}, {"name": "Moon", "sign": "Leo"}],
    "angles": [{"name": "Ascendant", "sign": "Sco"}],
}


@pytest.fixture
def lista(interpretacion_completa, settings):
    settings.WEB_BASE_URL = "https://astraguia.com"
    cuenta = interpretacion_completa.account
    cuenta.email = "lectora@example.com"
    cuenta.save()
    chart = interpretacion_completa.sujeto.natal_de
    chart.data = DATA
    chart.save()
    bd = chart.birth_data
    bd.name, bd.date, bd.place_label = "Ana", datetime.date(1985, 3, 14), "Rosario, Argentina"
    bd.save()
    primera = interpretacion_completa.secciones.order_by("orden").first()
    primera.texto = f"## Tu firma\n\n{ARRANQUE}\n\nUn segundo párrafo que no va en el mail."
    primera.save()
    return interpretacion_completa


def _chart(lista):
    return lista.sujeto.natal_de


def test_el_asunto_lleva_el_nombre(lista, resend):
    informe_service.avisar_informe_listo(lista)
    assert resend[0]["json"]["subject"] == "Tu informe está listo, Ana"


def test_sin_nombre_el_asunto_es_el_de_siempre(lista, resend):
    bd = _chart(lista).birth_data
    bd.name = None
    bd.save()
    informe_service.avisar_informe_listo(lista)
    assert resend[0]["json"]["subject"] == "Tu informe está listo"


def test_muestra_sol_luna_y_ascendente_en_palabras(lista, resend):
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    for esperado in ("Piscis", "Leo", "Escorpio", "Ascendente"):
        assert esperado in html, esperado


def test_no_lleva_la_fecha_ni_el_lugar_de_nacimiento(lista, resend):
    """Decisión del 10-10-2026: menos datos personales por mail. Quien lo
    recibe ya sabe cuándo y dónde nació; el mail no lo repite."""
    informe_service.avisar_informe_listo(lista)
    cuerpo = resend[0]["json"]
    for campo in ("html", "text", "subject"):
        assert "1985" not in cuerpo[campo] and "Rosario" not in cuerpo[campo], campo


def test_sin_hora_no_hay_ascendente(lista, resend):
    chart = _chart(lista)
    chart.data = {**DATA, "time_known": False, "angles": None}
    chart.save()
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    assert "Piscis" in html and "Escorpio" not in html and "Ascendente" not in html


def test_lleva_el_arranque_y_no_el_resto(lista, resend):
    informe_service.avisar_informe_listo(lista)
    cuerpo = resend[0]["json"]
    assert "Hay en tu carta una tensión" in cuerpo["html"]
    assert "segundo párrafo" not in cuerpo["html"] and "## " not in cuerpo["html"]
    assert cuerpo["text"].count("Hay en tu carta") == 1


def test_un_arranque_largo_se_corta_en_palabra_con_elipsis(lista, resend):
    primera = lista.secciones.order_by("orden").first()
    primera.texto = " ".join(["palabra"] * 200)
    primera.save()
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    assert html.count("palabra") < 60 and "…" in html


def test_trae_version_en_texto_plano_con_el_enlace(lista, resend):
    informe_service.avisar_informe_listo(lista)
    texto = resend[0]["json"]["text"]
    uuid = _chart(lista).uuid
    assert f"https://astraguia.com/es/carta/{uuid}" in texto and "<" not in texto


def test_el_nombre_y_el_arranque_se_escapan(lista, resend):
    bd = _chart(lista).birth_data
    bd.name = '<img src=x onerror="alert(1)">'
    bd.save()
    primera = lista.secciones.order_by("orden").first()
    primera.texto = "<script>alert(2)</script> y *negrita* del modelo."
    primera.save()
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    assert "<img src=x" not in html and "<script" not in html
    assert "&lt;script&gt;" in html and "*" not in html


def test_un_nombre_con_saltos_o_larguisimo_no_ensucia_el_asunto(lista, resend):
    bd = _chart(lista).birth_data
    bd.name = "Ana\r\nBcc: otro@example.com " + "x" * 300
    bd.save()
    informe_service.avisar_informe_listo(lista)
    asunto = resend[0]["json"]["subject"]
    assert "\n" not in asunto and "\r" not in asunto and len(asunto) <= len("Tu informe está listo, ") + 40


def test_en_ingles_los_signos_van_en_ingles(lista, resend):
    lista.lang = "en"
    lista.save()
    informe_service.avisar_informe_listo(lista)
    cuerpo = resend[0]["json"]
    assert cuerpo["subject"] == "Your report is ready, Ana"
    assert "Pisces" in cuerpo["html"] and "Scorpio" in cuerpo["html"]


def test_si_armar_el_enriquecimiento_falla_el_aviso_sale_igual(lista, resend, monkeypatch, caplog):
    def rompe(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(informe_service, "secciones_escritas", rompe)
    with caplog.at_level("ERROR", logger="api.informe_service"):
        informe_service.avisar_informe_listo(lista)
    assert len(resend) == 1
    assert resend[0]["json"]["subject"] == "Tu informe está listo"
    assert f"/es/carta/{_chart(lista).uuid}" in resend[0]["json"]["html"]
    assert any(r.exc_info for r in caplog.records)


# --- el vínculo ---


A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time": "06:10", "time_known": True, "lat": -31.42, "lng": -64.18}


@pytest.fixture
def vinculo_listo(make_account, settings):
    settings.WEB_BASE_URL = "https://astraguia.com"
    cuenta = make_account()
    cuenta.email = "lectora@example.com"
    cuenta.save()
    s = crear_vinculo(cuenta, "pareja", [{**A, "alias": "Ana"}, {**B, "alias": "Leo"}])
    interp = Interpretation.objects.create(
        sujeto=s, lang="es", prompt_version=PROMPT_VERSION, tier="largo", account=cuenta, completa=True,
    )
    InterpretationSection.objects.create(
        interpretation=interp, slug="encuentro", orden=0,
        texto="Persona A y Persona B comparten una calma que se nota.",
    )
    return interp


def test_el_vinculo_lleva_los_alias_y_su_pagina(vinculo_listo, resend):
    informe_service.avisar_informe_listo(vinculo_listo)
    cuerpo = resend[0]["json"]
    assert cuerpo["subject"] == "El informe de Ana y Leo está listo"
    assert "Ana y Leo comparten una calma" in cuerpo["html"] and "Persona A" not in cuerpo["html"]
    assert f'href="https://astraguia.com/es/vinculo/{vinculo_listo.sujeto.uuid}"' in cuerpo["html"]


def test_el_vinculo_sin_alias_dice_vinculo(vinculo_listo, resend):
    s = vinculo_listo.sujeto
    s.parametros = {**s.parametros, "alias": ["", ""]}
    s.save()
    informe_service.avisar_informe_listo(vinculo_listo)
    assert resend[0]["json"]["subject"] == "Tu informe de vínculo está listo"
    assert "Persona A y Persona B comparten" in resend[0]["json"]["html"]


# --- hallazgos del code review de de699b0 ---


def test_sin_arranque_el_boton_vuelve_a_decir_leer_mi_informe(lista, resend, monkeypatch):
    """Si el contexto no trae nada que mostrar, «Seguir leyendo» no continúa
    nada: el aviso simple conserva su botón de siempre."""
    monkeypatch.setattr(informe_service, "secciones_escritas", lambda *a: (_ for _ in ()).throw(RuntimeError()))
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    assert "Leer mi informe" in html and "Seguir leyendo" not in html


def test_el_markdown_del_arranque_no_llega_al_mail(lista, resend):
    primera = lista.secciones.order_by("orden").first()
    primera.texto = "Una _tensión_ con `código` y **negrita**, y snake_case intacto."
    primera.save()
    informe_service.avisar_informe_listo(lista)
    html = resend[0]["json"]["html"]
    assert "Una tensión con código y negrita" in html
    assert "_tensión_" not in html and "`" not in html and "snake_case" in html


def test_el_vinculo_deja_aire_entre_el_titulo_y_la_cita(vinculo_listo, resend):
    informe_service.avisar_informe_listo(vinculo_listo)
    html = resend[0]["json"]["html"]
    assert "height:14px" in html
