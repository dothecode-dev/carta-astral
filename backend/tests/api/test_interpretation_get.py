"""Leer una interpretación ya generada, sin volver a pedirla.

Hasta ahora sólo existía el POST, que crea o devuelve. Mostrar una lectura ya
escrita cada vez que alguien abre su carta consumía cupo del throttle de
generación y pedía por POST algo que no cambia nada.
"""

import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.chart_service import create_chart
from api.models import Account, Interpretation
from interpret.prompts import PROMPT_VERSION


@pytest.fixture
def cuenta(db):
    return Account.objects.create(email="lectura@ejemplo.test")


@pytest.fixture
def carta(cuenta):
    return create_chart(
        {"date": "1990-05-05", "time": "10:00", "lat": -34.6, "lng": -58.4,
         "name": "Prueba", "place_label": "Buenos Aires"},
        cuenta,
    )


@pytest.fixture
def cliente(cuenta):
    return APIClient(HTTP_AUTHORIZATION=f"Bearer {create_session(cuenta)}")


@pytest.mark.django_db
def test_devuelve_la_interpretacion_existente(cliente, carta):
    Interpretation.objects.create(
        chart=carta, lang="es", text="Un texto ya escrito.", prompt_version=PROMPT_VERSION,
        content_key="x", completa=True,
    )

    resp = cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo")

    assert resp.status_code == 200
    assert resp.json()["text"] == "Un texto ya escrito."
    assert resp.json()["lang"] == "es"
    assert resp.json()["disclaimer"]


@pytest.mark.django_db
def test_con_dos_productos_en_el_mismo_idioma_el_tier_del_query_param_decide(cliente, carta):
    """Fix round 1, Important 2 + Task 7: el filtro (`lang`, `prompt_version`)
    sin `tier` puede matchear DOS filas cuando la carta tiene la lectura
    breve Y el informe completo en el mismo idioma — RF9 los deja convivir a
    propósito. Sin filtrar por tier, cuál de las dos sirve el `.first()`
    queda a criterio del motor: entregar el informe completo a quien pidió
    la breve (o al revés) es entregar el producto equivocado. El tier viene
    del query param (RF20): pedir "corto" sirve la breve, pedir "largo" sirve
    el informe completo, sobre la MISMA carta y el MISMO idioma."""
    Interpretation.objects.create(
        chart=carta, lang="es", text="Lectura breve.", prompt_version=PROMPT_VERSION,
        tier="corto", completa=True,
    )
    Interpretation.objects.create(
        chart=carta, lang="es", text="Informe completo.", prompt_version=PROMPT_VERSION,
        tier="largo", completa=True,
    )

    resp_largo = cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo")
    assert resp_largo.status_code == 200
    assert resp_largo.json()["text"] == "Informe completo."

    resp_corto = cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=corto")
    assert resp_corto.status_code == 200
    assert resp_corto.json()["text"] == "Lectura breve."


@pytest.mark.django_db
def test_no_devuelve_200_vacio_mientras_se_genera(cliente, carta):
    """Task 10: `iniciar_generacion` crea la fila de entrada (completa=False,
    text="") apenas arranca la generación en el hilo de fondo. Antes de este
    fix, este GET devolvía 200 con `text=""` en ese estado: la web lo tomaba
    como éxito, mostraba una pantalla en blanco y no tenía botón de
    reintento. Un error acá lo puede manejar el cliente; un éxito vacío lo
    deja en un estado terminal sin salida."""
    Interpretation.objects.create(
        chart=carta, lang="es", text="", prompt_version=PROMPT_VERSION,
        content_key="x", completa=False,
    )

    resp = cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo")

    assert resp.status_code == 404
    # No la borra ni la toca: el hilo de fondo sigue escribiéndola.
    assert Interpretation.objects.filter(chart=carta, lang="es").exists()


@pytest.mark.django_db
def test_si_no_existe_devuelve_404_y_no_la_genera(cliente, carta):
    # Leer no puede gastar un crédito por la puerta de atrás.
    resp = cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo")

    assert resp.status_code == 404
    assert Interpretation.objects.filter(chart=carta).count() == 0


@pytest.mark.django_db
def test_no_devuelve_la_de_otro_idioma(cliente, carta):
    Interpretation.objects.create(
        chart=carta, lang="es", text="En español.", prompt_version=PROMPT_VERSION,
        content_key="x"
    )

    assert cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=en&tier=largo").status_code == 404


@pytest.mark.django_db
def test_no_devuelve_la_carta_de_otra_cuenta(carta, db):
    otra = Account.objects.create(email="ajena@ejemplo.test")
    ajeno = APIClient(HTTP_AUTHORIZATION=f"Bearer {create_session(otra)}")

    assert ajeno.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo").status_code == 404


@pytest.mark.django_db
def test_rechaza_un_idioma_que_no_existe(cliente, carta):
    assert cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=de&tier=largo").status_code == 400


@pytest.mark.django_db
def test_rechaza_un_tier_que_no_existe(cliente, carta):
    """Contrapunto de `test_rechaza_un_idioma_que_no_existe`: el tier
    tampoco tiene default, así que un valor desconocido —o ausente— es 400,
    no un 404 silencioso que sugiera "generá de nuevo"."""
    assert cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=premium").status_code == 400
    assert cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es").status_code == 400


@pytest.mark.django_db
def test_ignora_una_version_vieja_del_prompt(cliente, carta):
    # Si el prompt cambió, el texto guardado ya no corresponde a lo que hoy
    # generaría el sistema: para la web es como si no existiera.
    Interpretation.objects.create(
        chart=carta, lang="es", text="Escrita con otro prompt.", prompt_version="viejo",
        content_key="x"
    )

    assert cliente.get(f"/api/charts/{carta.uuid}/interpretation/?lang=es&tier=largo").status_code == 404
