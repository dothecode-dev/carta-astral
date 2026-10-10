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


def test_sustituye_los_alias_tambien_en_minuscula_y_sin_el_articulo():
    """A mitad de frase el modelo escribe «la persona A»: se reemplaza el
    grupo entero, para que no quede «la Ana»."""
    assert sustituir_alias("Entre la persona A y la persona B.", ("Ana", "Leo"), "es") == (
        "Entre Ana y Leo."
    )
    assert sustituir_alias("Le habla a la persona B.", ("Ana", "Leo"), "es") == "Le habla a Leo."
    assert sustituir_alias("Entre a pessoa A e a Pessoa B.", ("Ana", "Leo"), "pt") == "Entre Ana e Leo."
    assert sustituir_alias("The person A and Person B.", ("Ana", "Leo"), "en") == "Ana and Leo."


def test_sustituye_los_alias_en_los_tres_idiomas():
    assert sustituir_alias("Persona A y Persona B.", ("Ana", "Leo"), "es") == "Ana y Leo."
    assert sustituir_alias("Person A, Person B.", ("Ana", "Leo"), "en") == "Ana, Leo."
    assert sustituir_alias("Pessoa A, Pessoa B.", ("Ana", "Leo"), "pt") == "Ana, Leo."


def test_no_toca_la_preposicion_ni_un_alias_vacio():
    texto = "La persona a quien quiere. Persona A habla."
    assert sustituir_alias(texto, ("", ""), "es") == texto
    assert sustituir_alias(texto, ("Ana", "Leo"), "es") == "La persona a quien quiere. Ana habla."


def test_un_error_que_no_es_de_tier_no_se_disfraza_de_400(client_autenticado, monkeypatch):
    """`pedir` traduce a 400 sólo el tier que el producto no tiene; cualquier
    otro ValueError es un bug y tiene que subir (500, Sentry)."""
    from api import interpretation_service
    from api.canje import CapacidadAjena

    vid = _crear(client_autenticado).data["id"]

    def _explota(*a, **k):
        raise CapacidadAjena("bug")

    monkeypatch.setattr(interpretation_service, "iniciar_generacion", _explota)
    client_autenticado.raise_request_exception = True
    with pytest.raises(CapacidadAjena):
        client_autenticado.post(f"/api/vinculos/{vid}/informe/", {"lang": "es", "tier": "largo"}, format="json")


def test_el_vinculo_no_tiene_lectura_breve_por_la_api(client_autenticado):
    vid = _crear(client_autenticado).data["id"]
    r = client_autenticado.post(f"/api/vinculos/{vid}/informe/", {"lang": "es", "tier": "corto"}, format="json")
    assert r.status_code == 400


def test_cada_persona_trae_las_claves_que_la_web_ya_dibuja(client_autenticado):
    persona = _crear(client_autenticado).data["personas"][0]
    assert persona["interpretations"] == {} and persona["en_curso"] == {}
    assert persona["interpretation_langs"] == [] and "engine_version" in persona
    assert persona["birth"]["name"] is None
