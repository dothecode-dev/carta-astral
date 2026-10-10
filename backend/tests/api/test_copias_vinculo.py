"""RF12: una copia de vínculo no es alcanzable por ningún camino de carta."""

import uuid

import pytest
from django.db import connection
from django.utils import timezone

from api.models import BirthData, Chart

pytestmark = pytest.mark.django_db


@pytest.fixture
def copia(account):
    bd = BirthData.objects.create(date="1990-01-01", lat=0, lng=0, tz_name="UTC")
    return Chart.todas.create(
        birth_data=bd, data={}, engine_version="t", account=account, en_lista=False,
    )


# Cuerpos VÁLIDOS: con uno vacío, la validación de lang/tier responde 400
# antes de buscar la carta y el test no probaría nada.
@pytest.mark.parametrize("metodo,ruta,cuerpo", [
    ("get", "/api/charts/{}/", {}),
    ("patch", "/api/charts/{}/", {"trato": "neutro"}),
    ("get", "/api/charts/{}/interpretation/?lang=es&tier=largo", {}),
    ("post", "/api/charts/{}/interpretation/", {"lang": "es", "tier": "largo"}),
    ("get", "/api/charts/{}/interpretation/estado/?lang=es&tier=largo", {}),
    ("get", "/api/charts/{}/interpretation/secciones/?lang=es&tier=largo", {}),
    ("get", "/api/charts/{}/informe/indice/?lang=es", {}),
    ("post", "/api/charts/{}/pdf/", {}),
])
def test_ningun_camino_de_carta_alcanza_una_copia(client_autenticado, copia, metodo, ruta, cuerpo):
    r = getattr(client_autenticado, metodo)(ruta.format(copia.uuid), cuerpo, format="json")
    assert r.status_code == 404


def test_el_checkout_con_una_copia_es_404(client_autenticado, copia):
    r = client_autenticado.post(
        "/api/checkout/", {"producto": "informe_natal", "chart_id": str(copia.uuid)}, format="json",
    )
    assert r.status_code == 404


def test_la_copia_no_esta_en_la_lista(client_autenticado, copia, chart):
    ids = [c["id"] for c in client_autenticado.get("/api/charts/").data["results"]]
    assert str(chart.uuid) in ids and str(copia.uuid) not in ids


def test_una_carta_insertada_sin_en_lista_queda_visible(account):
    """El contenedor del deploy anterior no conoce la columna: la base la pone."""
    bd = BirthData.objects.create(date="1990-01-01", lat=0, lng=0, tz_name="UTC")
    nuevo = uuid.uuid4()
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO api_chart (uuid, birth_data_id, house_system, zodiac, data, "
            "engine_version, created_at, account_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            [nuevo.hex, bd.pk, "Placidus", "Tropical", "{}", "t", timezone.now(), account.pk],
        )
    assert Chart.objects.filter(uuid=nuevo).exists()
