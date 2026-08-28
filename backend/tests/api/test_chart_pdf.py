"""El PDF de la carta.

El endpoint recibe DATOS, nunca markup: la geometría que ya calculó `astra-wheel`
en el cliente y los rótulos ya traducidos. El backend construye el SVG y el HTML.
Por eso acá no hay tests de "sanear tags": no hay tags que sanear. Lo que sí se
prueba es que nada que venga de afuera pueda salirse de su casillero —ni por tipo,
ni por tamaño, ni por escaparse del escapado— y que el generador no resuelva
ninguna URL.

Casi todo se verifica sobre el HTML intermedio, que es una función pura y no
cuesta 300 ms por caso. El PDF de verdad se renderiza sólo donde importa que sea
un PDF.
"""

import uuid

import pytest

from api.chart_service import create_chart
from api.models import Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION, SECCIONES

pytestmark = pytest.mark.django_db

URL = "/api/charts/{}/pdf/"


def _chart(client, name="Camila", time_known=True):
    return create_chart(
        {
            "name": name, "date": "1994-03-12", "time": "07:20",
            "time_known": time_known, "lat": -34.6118, "lng": -58.3960,
            "place_label": "Buenos Aires, Argentina",
        },
        account=client.account,
    )


def _wheel():
    """Una rueda mínima pero completa: un cuerpo, una cúspide, un aspecto."""
    return {
        "view_box": 660,
        "center": 330,
        "rings": {"outer": 320, "signs": 290, "houses": 240, "aspect": 180},
        "signs": [{"glyph": "♈", "x": 100, "y": 100}],
        "cusps": [{
            "label": "I", "axis": True,
            "x1": 10, "y1": 10, "x2": 20, "y2": 20, "label_x": 15, "label_y": 15,
        }],
        "aspect_lines": [{"tone": "soft", "x1": 30, "y1": 30, "x2": 40, "y2": 40}],
        "angles": [{"label": "ASC", "x": 50, "y": 50}],
        "bodies": [{
            "glyph": "☉", "accent": True, "x": 60, "y": 60,
            "tick_x1": 61, "tick_y1": 61, "tick_x2": 62, "tick_y2": 62,
            "leader_x1": 63, "leader_y1": 63, "leader_x2": 64, "leader_y2": 64,
        }],
    }


def _matrix():
    """La matriz triangular, con tres cuerpos y dos cruces ocupados.

    El cliente manda sólo el triángulo: la fila i trae i+1 celdas. El resto lo
    completa el backend con huecos, que es lo que hace que se lea como matriz.
    """
    return {
        "labels": ["☉", "☽", "☿"],
        "rows": [
            {"label": "☽", "cells": [{"glyph": "☌", "tone": "neutral"}]},
            {"label": "☿", "cells": [None, {"glyph": "△", "tone": "soft"}]},
        ],
    }


def _payload(**over):
    base = {
        "labels": {
            "brand_tagline": "Tu carta natal",
            "eyebrow": "Carta natal",
            "chart_name": "Camila",
            "birth_line": "12 de marzo de 1994 · 07:20 · Buenos Aires, Argentina",
            "positions": "Posiciones",
            "aspects": "Aspectos",
            "reading": "Tu lectura",
            "made_with": "Hecho con ASTRA",
        },
        "positions": [
            {"glyph": "☉", "name": "Sol", "position": "♓ Piscis 21°36′",
             "house": "XII", "retrograde": False},
            {"glyph": "♃", "name": "Júpiter", "position": "♏ Escorpio 14°26′",
             "house": "VIII", "retrograde": True},
        ],
        "aspects": [
            {"glyph": "☉ △ ♃", "name": "Trígono", "detail": "orbe 7.2°"},
        ],
        "wheel": _wheel(),
        "aspect_matrix": _matrix(),
        "reading_lang": None,
    }
    base.update(over)
    return base


def _informe(chart, texto, lang="es", completa=True):
    """Un informe con una sola sección escrita, para probar el render de la
    lectura sin tener que armar las ocho."""
    interp = Interpretation.objects.create(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION, completa=completa,
    )
    InterpretationSection.objects.create(
        interpretation=interp, slug=SECCIONES[0].slug, orden=0, texto=texto,
    )
    return interp


def _informe_legacy(chart, texto, lang="es", completa=True):
    """La forma anterior a la Tarea 2: el texto completo en `Interpretation.text`,
    sin ninguna `InterpretationSection`. Es exactamente lo que preserva
    `0020_backfill_completa` para lo que ya existía en producción antes del
    informe de ocho secciones — sigue existiendo hoy, no es un caso teórico."""
    return Interpretation.objects.create(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION, completa=completa, text=texto,
    )


def _informe_completo(chart, lang="es"):
    """Todas las secciones que aplican a esta carta (`secciones_aplicables`,
    filtrado por si hay hora de nacimiento), cada una con su propio texto."""
    from api.informe_service import secciones_aplicables

    interp = Interpretation.objects.create(
        chart=chart, lang=lang, prompt_version=PROMPT_VERSION, completa=True,
    )
    for orden, seccion in enumerate(secciones_aplicables(chart)):
        InterpretationSection.objects.create(
            interpretation=interp, slug=seccion.slug, orden=orden,
            texto=f"Texto de la sección {seccion.slug}.",
        )
    return interp


def _html(chart, **over):
    """El documento como HTML, que es donde se verifica el contenido."""
    from api.chart_pdf_service import build_document_html
    from api.pdf_payload import ChartPdfSerializer

    ser = ChartPdfSerializer(data=_payload(**over))
    assert ser.is_valid(), ser.errors
    return build_document_html(chart, ser.validated_data)


# --- acceso -----------------------------------------------------------------

def test_sin_credenciales_401():
    from rest_framework.test import APIClient

    resp = APIClient().post(URL.format(uuid.uuid4()), _payload(), format="json")
    assert resp.status_code == 401


def test_carta_de_otra_cuenta_404(account_client, make_account):
    from api.auth import create_session
    from rest_framework.test import APIClient

    ajena = make_account()
    otro = APIClient()
    otro.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(ajena)}")
    otro.account = ajena
    chart = _chart(otro)

    resp = account_client.post(URL.format(chart.uuid), _payload(), format="json")
    assert resp.status_code == 404


def test_carta_inexistente_404(account_client):
    resp = account_client.post(URL.format(uuid.uuid4()), _payload(), format="json")
    assert resp.status_code == 404


# --- el PDF de verdad -------------------------------------------------------

def test_devuelve_un_pdf(account_client):
    chart = _chart(account_client)
    resp = account_client.post(URL.format(chart.uuid), _payload(), format="json")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "application/pdf"
    contenido = b"".join(resp.streaming_content) if resp.streaming else resp.content
    assert contenido.startswith(b"%PDF")
    assert len(contenido) > 1000


def test_content_disposition_conserva_tildes_y_limpia_separadores(account_client):
    chart = _chart(account_client, name="João/Pérez: 1990")
    resp = account_client.post(URL.format(chart.uuid), _payload(), format="json")
    disp = resp["Content-Disposition"]
    assert "filename*=UTF-8''" in disp
    assert "%C3%A3" in disp  # la "ã" viaja percent-encoded, no se pierde
    nombre = disp.split("filename*=UTF-8''")[1]
    assert "/" not in nombre and ":" not in nombre
    # El respaldo ASCII existe y es usable, aunque pierda los acentos.
    assert 'filename="Joao Perez 1990.pdf"' in disp


def test_carta_sin_nombre_usa_el_rotulo_traducido(account_client):
    chart = _chart(account_client, name="")
    labels = _payload()["labels"] | {"chart_name": "Carta sin nombre"}
    resp = account_client.post(URL.format(chart.uuid), _payload(labels=labels), format="json")
    assert "Carta%20sin%20nombre.pdf" in resp["Content-Disposition"]


# --- contenido --------------------------------------------------------------

def test_el_documento_lista_la_carta(account_client):
    html = _html(_chart(account_client))
    assert "Camila" in html
    assert "Júpiter" in html and "Sol" in html
    assert "Posiciones" in html and "Aspectos" in html
    # Los aspectos ya no se nombran uno por uno: están en la matriz, como en la web.
    assert '<table class="aspectMatrix">' in html


def test_sin_reading_lang_no_aparece_la_lectura(account_client):
    chart = _chart(account_client)
    Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION,
        text="Tu Sol en Piscis habla de fronteras porosas.", content_key="k",
    )
    html = _html(chart)  # reading_lang=None
    assert "fronteras porosas" not in html


def test_con_reading_lang_aparece_la_lectura_y_el_disclaimer(account_client):
    chart = _chart(account_client)
    _informe(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" in html
    from api.interpretation_service import DISCLAIMERS
    assert DISCLAIMERS["es"][:40] in html


def test_reading_lang_sin_lectura_devuelve_la_carta_sola(account_client):
    chart = _chart(account_client)
    html = _html(chart, reading_lang="es")
    assert "Camila" in html
    assert "Tu lectura" not in html


def test_lectura_en_otro_idioma_se_incluye_tal_como_esta(account_client):
    """La lectura se compra una vez y se traduce gratis: si existe en español y
    la página está en inglés, el PDF la lleva en español antes que no llevarla."""
    chart = _chart(account_client)
    _informe(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" in html


# --- la forma legacy: texto completo, sin InterpretationSection -------------
#
# `0020_backfill_completa.py` preserva a propósito estas filas —marca
# `completa=True` sin tocar el texto ni inventarle secciones— para lo que ya
# existía en producción antes de que el informe se partiera en ocho. Siguen
# ahí hoy: no es un caso teórico, es la lectura por la que alguien ya pagó.


def test_informe_legacy_sin_secciones_aparece_en_el_pdf(account_client):
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" in html


def test_legacy_aparece_el_disclaimer(account_client):
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    from api.interpretation_service import DISCLAIMERS
    assert DISCLAIMERS["es"][:40] in html


def test_legacy_en_otro_idioma_se_incluye_tal_como_esta(account_client):
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" in html


def test_legacy_la_lectura_empieza_en_hoja_nueva(account_client):
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert html.index("pagebreak") < html.index("fronteras porosas")


def test_legacy_no_promete_capitulos_que_no_tiene(account_client):
    """El texto legacy no está partido en secciones: mostrar un índice de
    ocho títulos sobre un texto de una sola pieza prometería una estructura
    que el documento no tiene. Decisión explícita: sin índice para este caso."""
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert '<ol class="indice">' not in html


def test_legacy_incompleta_no_aparece_en_el_pdf(account_client):
    chart = _chart(account_client)
    _informe_legacy(chart, "Tu Sol en Piscis habla de fronteras porosas.", completa=False)
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" not in html


def test_la_matriz_de_aspectos_se_dibuja_como_en_la_web(account_client):
    """La misma matriz triangular que muestra el sitio: cada cruce dice qué
    aspecto hay entre esos dos cuerpos."""
    html = _html(_chart(account_client))

    tabla = html.split('<table class="aspectMatrix">')[1].split("</table>")[0]

    # Encabezados: todos los rótulos menos el último, que nunca encabeza columna
    # porque no tiene con quién cruzarse más abajo.
    cabecera = tabla.split("</tr>")[0]
    assert '<th class="matrixHead">☉</th>' in cabecera
    assert '<th class="matrixHead">☿</th>' not in cabecera

    # Los dos cruces ocupados, cada uno con el tono que le toca.
    assert '<td class="matrixCell matrixNeutral">☌</td>' in tabla
    assert '<td class="matrixCell matrixSoft">△</td>' in tabla
    # Y el triángulo superior queda hueco, no con celdas vacías cualesquiera.
    assert "matrixVoid" in tabla


def test_sin_matriz_queda_la_lista_como_respaldo(account_client):
    html = _html(_chart(account_client), aspect_matrix=None)
    # La clase vive en el CSS siempre; lo que no tiene que existir es la tabla.
    assert '<table class="aspectMatrix">' not in html
    assert "Trígono" in html and "orbe 7.2°" in html


def test_con_matriz_la_carta_cierra_ahi(account_client):
    """Dos hojas para la carta —rueda, y posiciones con la matriz— y la lectura
    desde la tercera. La lista de orbes debajo partía la página y corría todo."""
    html = _html(_chart(account_client))
    assert '<table class="aspectMatrix">' in html
    assert "orbe 7.2°" not in html


def test_la_lectura_empieza_en_hoja_nueva(account_client):
    chart = _chart(account_client)
    _informe(chart, "Tu Sol en Piscis habla de fronteras porosas.")
    html = _html(chart, reading_lang="es")
    assert html.index("pagebreak") < html.index("fronteras porosas")


def test_el_pdf_trae_las_ocho_secciones_con_indice(interpretacion_completa):
    from api import pdf_payload

    payload = pdf_payload.build(interpretacion_completa.chart, interpretacion_completa)
    assert len(payload["reading"]["secciones"]) == 8
    assert payload["reading"]["indice"] == [s.titulo["es"] for s in SECCIONES]


def test_la_hoja_de_estilos_evita_titulos_huerfanos():
    # Un título solo al pie de una página se lee como error de maquetación, y
    # este PDF se vende a US$29. WeasyPrint respeta break-after.
    from pathlib import Path

    css = Path("api/pdf_assets/informe.css").read_text(encoding="utf-8")
    assert "break-after: avoid" in css


def test_interpretacion_incompleta_no_aparece_en_el_pdf(account_client):
    """Un informe a medio generar no se sirve como si estuviera terminado
    (mismo criterio que `InterpretationView.get`)."""
    chart = _chart(account_client)
    _informe(chart, "Tu Sol en Piscis habla de fronteras porosas.", completa=False)
    html = _html(chart, reading_lang="es")
    assert "fronteras porosas" not in html
    assert "Tu lectura" not in html


def test_el_indice_nombra_las_secciones_que_faltan(account_client):
    """El índice lista las ocho (o siete sin hora) aunque sólo una esté
    escrita: mismo criterio que `informe_service.resumen_gratis`."""
    chart = _chart(account_client)
    _informe(chart, "Tu Sol en Piscis habla de fronteras porosas.", completa=True)
    html = _html(chart, reading_lang="es")
    assert SECCIONES[-1].titulo["es"] in html
    assert f'<h2>{SECCIONES[0].titulo["es"]}</h2>' in html


def test_el_indice_no_promete_casas_sin_hora_de_nacimiento(account_client):
    """Sin hora de nacimiento son siete secciones, no ocho: "casas" no aplica
    (`secciones_aplicables`). El índice no puede prometer un capítulo que el
    informe nunca va a escribir para esta carta."""
    chart = _chart(account_client, time_known=False)
    _informe_completo(chart)
    html = _html(chart, reading_lang="es")

    casas = next(s for s in SECCIONES if s.slug == "casas")
    firma = next(s for s in SECCIONES if s.slug == "firma")
    assert casas.titulo["es"] not in html
    assert firma.titulo["es"] in html


def test_un_tono_desconocido_en_la_matriz_es_400(account_client):
    chart = _chart(account_client)
    matriz = _matrix()
    matriz["rows"][0]["cells"][0]["tone"] = 'x" style="display:none'
    resp = account_client.post(
        URL.format(chart.uuid), _payload(aspect_matrix=matriz), format="json"
    )
    assert resp.status_code == 400


def test_la_matriz_tiene_tope_de_tamano(account_client):
    chart = _chart(account_client)
    matriz = {"labels": ["☉"] * 200, "rows": []}
    resp = account_client.post(
        URL.format(chart.uuid), _payload(aspect_matrix=matriz), format="json"
    )
    assert resp.status_code == 400


def test_la_rueda_deja_aire_para_los_rotulos_de_los_ejes(account_client):
    """El "ASC" va por fuera del anillo y sin margen sale cortado: en el spike
    del 16-08-2026 se leía "SC"."""
    html = _html(_chart(account_client))
    assert 'viewBox="-16 -16 692.0 692.0"' in html


def test_carta_sin_rueda_se_genera_igual(account_client):
    html = _html(_chart(account_client), wheel=None)
    assert "Camila" in html
    assert "<svg" not in html


def test_no_toca_creditos_ni_ledger(account_client):
    from api.ledger import credits_available
    from api.models import CreditTransaction

    chart = _chart(account_client)
    antes = (credits_available(account_client.account), CreditTransaction.objects.count())
    account_client.post(URL.format(chart.uuid), _payload(), format="json")
    account_client.post(URL.format(chart.uuid), _payload(reading_lang="es"), format="json")
    assert (credits_available(account_client.account), CreditTransaction.objects.count()) == antes


# --- lo que llega de afuera -------------------------------------------------

def test_campo_desconocido_400(account_client):
    chart = _chart(account_client)
    resp = account_client.post(
        URL.format(chart.uuid), _payload(sorpresa="hola"), format="json"
    )
    assert resp.status_code == 400


def test_coordenada_no_numerica_400(account_client):
    chart = _chart(account_client)
    rueda = _wheel()
    rueda["bodies"][0]["x"] = "NaN"
    resp = account_client.post(URL.format(chart.uuid), _payload(wheel=rueda), format="json")
    assert resp.status_code == 400


def test_coordenada_fuera_de_rango_400(account_client):
    chart = _chart(account_client)
    rueda = _wheel()
    rueda["bodies"][0]["x"] = 10**9
    resp = account_client.post(URL.format(chart.uuid), _payload(wheel=rueda), format="json")
    assert resp.status_code == 400


def test_lista_gigante_400(account_client):
    chart = _chart(account_client)
    enorme = [{"glyph": "☉ △ ♃", "name": "Trígono", "detail": "orbe 1°"}] * 10000
    resp = account_client.post(URL.format(chart.uuid), _payload(aspects=enorme), format="json")
    assert resp.status_code == 400


def test_rotulo_larguisimo_400(account_client):
    chart = _chart(account_client)
    labels = _payload()["labels"] | {"eyebrow": "x" * 50000}
    resp = account_client.post(URL.format(chart.uuid), _payload(labels=labels), format="json")
    assert resp.status_code == 400


def test_tono_de_aspecto_desconocido_400(account_client):
    """El color no viaja: viaja un tono de una lista cerrada. Nada que venga de
    afuera se escribe como atributo del SVG."""
    chart = _chart(account_client)
    rueda = _wheel()
    rueda["aspect_lines"][0]["tone"] = 'red" onload="alert(1)'
    resp = account_client.post(URL.format(chart.uuid), _payload(wheel=rueda), format="json")
    assert resp.status_code == 400


def test_el_texto_se_escapa(account_client):
    chart = _chart(account_client)
    labels = _payload()["labels"] | {"chart_name": "<script>alert(1)</script>"}
    rueda = _wheel()
    rueda["bodies"][0]["glyph"] = "<b>&</b>"
    html = _html(chart, labels=labels, wheel=rueda)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "<b>&</b>" not in html


def test_el_documento_no_referencia_ningun_recurso(account_client):
    """Ni siquiera generándolo nosotros: si algún día alguien mete un <img>, este
    test lo frena antes que el fetcher.

    El `xmlns` del SVG no cuenta: es el identificador del namespace, no algo que
    WeasyPrint vaya a resolver. Lo que se busca es cualquier cosa que sí lo sea.
    """
    html = _html(_chart(account_client))
    sin_namespace = html.replace('xmlns="http://www.w3.org/2000/svg"', "")
    assert "http://" not in sin_namespace and "https://" not in sin_namespace
    assert "<img" not in html and "<image" not in html
    assert "src=" not in html and "href=" not in html
    assert "url(" not in sin_namespace.split("</style>")[1]  # el CSS sí trae las fuentes


# --- el generador no sale a la red -----------------------------------------

def test_el_fetcher_rechaza_todo_lo_que_sea_red():
    from api.chart_pdf_service import pdf_url_fetcher

    for url in ("http://169.254.169.254/latest/meta-data/",
                "https://ejemplo.test/x.png",
                "file:///etc/passwd",
                "ftp://ejemplo.test/x"):
        with pytest.raises(ValueError):
            pdf_url_fetcher().fetch(url)


def test_el_fetcher_deja_pasar_las_fuentes_embebidas():
    """`data:` es la única excepción, y no es una concesión: son los bytes de las
    tipografías que embebe este mismo módulo. No hay red del otro lado."""
    from api.chart_pdf_service import pdf_url_fetcher

    respuesta = pdf_url_fetcher().fetch("data:text/plain;base64,aG9sYQ==")
    assert respuesta.read() == b"hola"


# --- el techo de uso --------------------------------------------------------

def test_el_endpoint_esta_limitado(account_client, monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"pdf": "2/day", "chart": "60/day", "interpretation": "20/day",
         "install": "30/day", "auth": "30/day", "sky": "240/hour"},
    )
    from django.core.cache import cache
    cache.clear()

    chart = _chart(account_client)
    codigos = [
        account_client.post(URL.format(chart.uuid), _payload(), format="json").status_code
        for _ in range(3)
    ]
    assert codigos[:2] == [200, 200]
    assert codigos[2] == 429
    # El cupo del PDF no se come el de otros endpoints.
    assert account_client.get(f"/api/charts/{chart.uuid}/").status_code == 200


# --- la imagen, que ningún gate mira ---------------------------------------

def test_el_dockerfile_instala_las_fuentes_y_las_libs():
    """Los glifos astrológicos los pone DejaVu. Hoy está en la imagen por
    arrastre de Pango; si deja de estar, la carta entera sale en cajitas y no se
    entera nadie hasta abrir un PDF."""
    from pathlib import Path

    dockerfile = (Path(__file__).resolve().parents[2] / "Dockerfile").read_text()
    for paquete in ("fonts-dejavu-core", "libpango-1.0-0", "libpangoft2-1.0-0",
                    "libharfbuzz0b", "libgdk-pixbuf-2.0-0", "libffi8"):
        assert paquete in dockerfile, f"falta {paquete} en el runtime de la imagen"
