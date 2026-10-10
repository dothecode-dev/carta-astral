import pytest

from api.vinculo_api import sustituir_alias

pytestmark = pytest.mark.django_db

A = {"date": "1985-03-14", "time": "08:30", "time_known": True, "lat": -32.95, "lng": -60.65}
B = {"date": "1988-09-09", "time_known": False, "lat": -31.42, "lng": -64.18}


@pytest.fixture(autouse=True)
def encendido(settings):
    settings.VINCULO_ENABLED = True


def _crear(cliente, **extra):
    return cliente.post("/api/vinculos/", {"tipo": "amistad", "personas": [A, B], **extra}, format="json")


def test_crear_y_leer(client_autenticado):
    r = _crear(client_autenticado)
    assert r.status_code == 201
    assert client_autenticado.get(f"/api/vinculos/{r.data['id']}/").status_code == 200
    assert [v["id"] for v in client_autenticado.get("/api/vinculos/").data["results"]] == [r.data["id"]]


@pytest.mark.parametrize("cuerpo,motivo", [
    ({"tipo": "familia", "personas": [{**A, "rol": "progenitor"}, {**B, "rol": "progenitor"}]}, "combinacion_invalida"),
    ({"tipo": "trabajo", "personas": [{**A, "rol": "hijo"}, {**B, "rol": "equipo"}]}, "rol_invalido"),
    ({"tipo": "amistad", "personas": [{**A, "date": "1985-03"}, B]}, "datos_invalidos"),
    ({"tipo": "amistad", "personas": [A, A]}, "misma_persona"),
])
def test_rechazos_400(client_autenticado, cuerpo, motivo):
    r = client_autenticado.post("/api/vinculos/", cuerpo, format="json")
    assert r.status_code == 400 and r.data["error"] == motivo


def test_un_vinculo_ajeno_es_404(client_autenticado, account_client):
    vid = _crear(account_client).data["id"]
    for ruta in ("/", "/informe/?lang=es&tier=largo", "/informe/estado/?lang=es&tier=largo"):
        assert client_autenticado.get(f"/api/vinculos/{vid}{ruta}").status_code == 404


def test_con_el_flag_apagado_todo_es_404(client_autenticado, settings):
    vid = _crear(client_autenticado).data["id"]
    settings.VINCULO_ENABLED = False
    assert _crear(client_autenticado).status_code == 404
    assert client_autenticado.get("/api/vinculos/").status_code == 404
    assert client_autenticado.get(f"/api/vinculos/{vid}/").status_code == 404


def test_sustituye_los_alias_en_los_tres_idiomas():
    texto = "Persona A y Persona B. Person A, Pessoa B. La persona a quien quiere."
    assert sustituir_alias(texto, ("Ana", "Leo")) == (
        "Ana y Leo. Ana, Leo. La persona a quien quiere."
    )
    assert sustituir_alias(texto, ("", "")) == texto
