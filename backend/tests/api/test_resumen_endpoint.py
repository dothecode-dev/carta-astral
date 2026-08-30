import pytest

from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db


@pytest.fixture
def chart_sin_hora(account):
    """Una carta sin hora de nacimiento, de la misma cuenta que `chart`
    comparte con `client_autenticado`: `secciones_aplicables` filtra por
    `chart.data["time_known"]`, no por `BirthData.time_known`, pero se arma
    también sin hora ahí para no dejar el fixture inconsistente."""
    bd = BirthData.objects.create(date="2000-01-01", time_known=False, lat=0, lng=0, tz_name="UTC")
    return Chart.objects.create(
        birth_data=bd, data={"time_known": False}, engine_version="test", account=account,
    )


def test_el_indice_lista_las_ocho_secciones_sin_informe_generado(client_autenticado, chart):
    # `client_autenticado` y `chart` comparten cuenta (fixture `account`) a
    # propósito: `account_client` crea su PROPIA cuenta, distinta de la dueña
    # de `chart`, así que ese combo da 404 siempre y no prueba nada del
    # índice (mismo hallazgo que documenta test_charts_scoping.py).
    datos = client_autenticado.get(f"/api/charts/{chart.uuid}/informe/indice/?lang=es").json()
    assert len(datos) == 8
    assert datos[0]["titulo"] == "Tu firma"
    assert datos[0]["parrafo"] == ""
    assert datos[0]["restante"] == 900


def test_sin_hora_de_nacimiento_son_siete(client_autenticado, chart_sin_hora):
    datos = client_autenticado.get(
        f"/api/charts/{chart_sin_hora.uuid}/informe/indice/?lang=es"
    ).json()
    assert len(datos) == 7
    assert "casas" not in [e["slug"] for e in datos]


def test_el_indice_es_de_la_cuenta_duena(account_client, chart):
    # Caso armado a propósito para probar scoping, no un mismatch accidental
    # de fixtures: `chart` es de la cuenta de `account` y `account_client`
    # crea otra cuenta distinta a propósito, así que el 404 sí certifica que
    # una carta ajena no se puede consultar.
    r = account_client.get(f"/api/charts/{chart.uuid}/informe/indice/?lang=es")
    assert r.status_code == 404


def test_el_indice_muestra_el_arranque_de_lo_ya_generado(
    client_autenticado, interpretacion_completa,
):
    # `interpretacion_completa` cuelga de `chart`/`account`, igual que
    # `client_autenticado`: mismo motivo que el primer test de este archivo.
    chart = interpretacion_completa.chart
    datos = client_autenticado.get(f"/api/charts/{chart.uuid}/informe/indice/?lang=es").json()
    assert len(datos) == 8
    assert datos[0]["parrafo"] == "Texto de la sección firma."


def test_lang_invalido_da_400(client_autenticado, chart):
    r = client_autenticado.get(f"/api/charts/{chart.uuid}/informe/indice/?lang=fr")
    assert r.status_code == 400
