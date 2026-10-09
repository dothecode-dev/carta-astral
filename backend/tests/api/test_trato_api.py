"""El trato del lector entra por la API (RF2, RF3): al crear la carta, en el
checkout anónimo y con un PATCH sobre la carta."""

import pytest
from rest_framework.test import APIClient

from api import stripe_client
from api.auth import create_session
from api.models import Account, BirthData, Chart, Interpretation, PasarelaCheckout
from api.sujetos import sujeto_natal
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

DATOS = {"date": "1990-05-10", "time": "14:30", "time_known": True, "lat": -34.6, "lng": -58.4,
         "place_label": "Buenos Aires, AR", "locale": "es"}


def _client(acc):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    return c


@pytest.fixture
def cuenta():
    return Account.objects.create()


@pytest.fixture
def carta(cuenta):
    r = _client(cuenta).post("/api/charts/", DATOS, format="json")
    assert r.status_code == 201
    return Chart.objects.get(uuid=r.data["id"])


# --- POST /api/charts/ ---

def test_crear_con_trato_lo_guarda(cuenta):
    r = _client(cuenta).post("/api/charts/", {**DATOS, "trato": "femenino"}, format="json")
    assert r.status_code == 201
    assert r.data["trato"] == "femenino"
    assert BirthData.objects.get().trato == "femenino"


def test_crear_sin_trato_queda_vacio(cuenta):
    r = _client(cuenta).post("/api/charts/", DATOS, format="json")
    assert r.status_code == 201
    assert BirthData.objects.get().trato == ""


def test_crear_con_trato_invalido_da_400_y_no_crea_carta(cuenta):
    r = _client(cuenta).post("/api/charts/", {**DATOS, "trato": "otro"}, format="json")
    assert r.status_code == 400
    assert r.json() == {"error": "trato inválido"}
    assert Chart.objects.count() == 0 and BirthData.objects.count() == 0


# --- POST /api/checkout/anonimo/ ---

@pytest.fixture
def stripe_responde(monkeypatch, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    settings.STRIPE_SUCCESS_URL = (
        "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"
    )

    class _Sesion:
        id = "cs_test_nueva1"
        url = "https://checkout.stripe.com/c/pay/cs_test_nueva1"

    monkeypatch.setattr(
        stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **p: _Sesion())
    )


def _anonimo(client, cuerpo):
    return client.post("/api/checkout/anonimo/", cuerpo, content_type="application/json")


def test_checkout_anonimo_guarda_el_trato(client, stripe_responde):
    r = _anonimo(client, {**DATOS, "trato": "masculino"})
    assert r.status_code == 200
    assert Chart.objects.get().birth_data.trato == "masculino"


def test_checkout_anonimo_con_trato_invalido_da_400_sin_carta_ni_fila(client, stripe_responde):
    r = _anonimo(client, {**DATOS, "trato": "otro"})
    assert r.status_code == 400
    assert r.json()["error"] == "trato inválido"
    assert Chart.objects.count() == 0 and PasarelaCheckout.objects.count() == 0


# --- PATCH /api/charts/<uuid>/ ---

def _patch(client, carta, cuerpo):
    return client.patch(f"/api/charts/{carta.uuid}/", cuerpo, format="json")


def test_patch_del_dueno_cambia_el_trato(cuenta, carta):
    r = _patch(_client(cuenta), carta, {"trato": "neutro"})
    assert r.status_code == 200
    assert r.data["trato"] == "neutro" and r.data["id"] == str(carta.uuid)
    carta.birth_data.refresh_from_db()
    assert carta.birth_data.trato == "neutro"


def test_patch_de_otra_cuenta_da_404_sin_cambio(carta):
    otra = Account.objects.create()
    r = _patch(_client(otra), carta, {"trato": "neutro"})
    assert r.status_code == 404
    carta.birth_data.refresh_from_db()
    assert carta.birth_data.trato == ""


def test_patch_con_trato_invalido_da_400_sin_cambio(cuenta, carta):
    _patch(_client(cuenta), carta, {"trato": "femenino"})
    r = _patch(_client(cuenta), carta, {"trato": "otro"})
    assert r.status_code == 400
    assert r.json() == {"error": "trato inválido"}
    carta.birth_data.refresh_from_db()
    assert carta.birth_data.trato == "femenino"


def test_patch_sin_la_clave_trato_da_400_sin_cambio(cuenta, carta):
    """Un PATCH sin la clave no dice nada sobre el trato: no puede borrarlo."""
    _patch(_client(cuenta), carta, {"trato": "femenino"})
    r = _patch(_client(cuenta), carta, {})
    assert r.status_code == 400
    assert r.json() == {"error": "trato inválido"}
    carta.birth_data.refresh_from_db()
    assert carta.birth_data.trato == "femenino"


@pytest.mark.parametrize("cuerpo", [{"trato": None}, {"trato": ""}])
def test_patch_sin_clave_o_null_es_sin_elegir(cuenta, carta, cuerpo):
    """Con null o "" = «sin elegir» (""), igual que `validar_trato`."""
    _patch(_client(cuenta), carta, {"trato": "femenino"})
    r = _patch(_client(cuenta), carta, cuerpo)
    assert r.status_code == 200 and r.data["trato"] == ""
    carta.birth_data.refresh_from_db()
    assert carta.birth_data.trato == ""


def test_patch_no_cambia_el_trato_de_una_interpretacion_existente(cuenta, carta):
    """RF3: el informe ya escrito conserva el trato con el que nació."""
    interp = Interpretation.objects.create(
        sujeto=sujeto_natal(carta), chart=carta, lang="es", tier="largo", prompt_version=PROMPT_VERSION,
        completa=True, trato="femenino",
    )
    r = _patch(_client(cuenta), carta, {"trato": "masculino"})
    assert r.status_code == 200
    interp.refresh_from_db()
    assert interp.trato == "femenino"


# --- GET ---

def test_detalle_y_listado_devuelven_el_trato(cuenta):
    c = _client(cuenta)
    c.post("/api/charts/", {**DATOS, "trato": "neutro"}, format="json")
    chart = Chart.objects.get()
    assert c.get(f"/api/charts/{chart.uuid}/").json()["trato"] == "neutro"
    assert c.get("/api/charts/").json()["results"][0]["trato"] == "neutro"
