import pytest

from api.vinculo_pdf import build_vinculo_html

pytestmark = pytest.mark.django_db

A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time_known": False, "lat": -31.42, "lng": -64.18}
LABELS = {k: "x" for k in ("brand_tagline", "eyebrow", "chart_name", "birth_line", "positions",
                          "aspects", "reading", "made_with")}


def test_dos_ruedas_y_alias_escapado(make_account, interpretacion_vinculo_completa):
    s = interpretacion_vinculo_completa.sujeto  # alias A = "<b>Ana</b>"
    html = build_vinculo_html(s, {
        "labels": {**LABELS, "persona_a": "<b>Ana</b>", "persona_b": "Leo"},
        "wheels": [None, None], "aspects": [], "reading_lang": "es",
    })
    assert "<b>Ana</b>" not in html and "&lt;b&gt;Ana&lt;/b&gt;" in html
    assert "Persona A" not in html  # sustituido en la lectura


def test_el_pdf_de_un_vinculo_ajeno_es_404(client_autenticado, account_client, settings):
    settings.VINCULO_ENABLED = True
    vid = account_client.post("/api/vinculos/", {"tipo": "amistad", "personas": [A, B]}, format="json").data["id"]
    assert client_autenticado.post(f"/api/vinculos/{vid}/pdf/", {}, format="json").status_code == 404


def _cliente(cuenta):
    from rest_framework.test import APIClient

    from api.auth import create_session

    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(cuenta)}")
    return cliente


def test_el_pdf_propio_es_un_pdf(interpretacion_vinculo_completa):
    s = interpretacion_vinculo_completa.sujeto
    r = _cliente(s.account).post(f"/api/vinculos/{s.uuid}/pdf/", {
        "labels": {**LABELS, "persona_a": "Ana", "persona_b": "Leo"},
        "wheels": [None, None], "aspects": [], "reading_lang": "es",
    }, format="json")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-")


def test_las_secciones_llegan_con_los_alias(interpretacion_vinculo_completa):
    """RF22 al mostrar: el modelo escribió «Persona A»; la API devuelve el alias."""
    s = interpretacion_vinculo_completa.sujeto
    r = _cliente(s.account).get(f"/api/vinculos/{s.uuid}/informe/secciones/?lang=es&tier=largo")
    assert r.status_code == 200
    assert r.data["secciones"][0]["texto"] == "<b>Ana</b> conoce a Leo."


def test_el_indice_llega_con_los_alias(interpretacion_vinculo_completa):
    """El arranque de cada sección del índice es texto del modelo: RF22 también."""
    s = interpretacion_vinculo_completa.sujeto
    r = _cliente(s.account).get(f"/api/vinculos/{s.uuid}/informe/indice/?lang=es")
    assert r.status_code == 200
    textos = " ".join(str(v) for item in r.data for v in item.values())
    assert "Persona A" not in textos and "<b>Ana</b>" in textos
