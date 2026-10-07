"""`POST /api/checkout/anonimo/`: abrir el pago del informe sin cuenta (RF1-RF4b)."""

import pytest
from django.core.cache import cache

from api import identity, mantenimiento, stripe_client
from api.models import Chart, Cupon, PasarelaCheckout

pytestmark = pytest.mark.django_db
URL = "/api/checkout/anonimo/"
DATOS = {"date": "1990-05-10", "time": "14:30", "time_known": True, "lat": -34.6, "lng": -58.4,
         "place_label": "Buenos Aires, AR", "locale": "es"}


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_SECRET_KEY = "sk_test_de_prueba"
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}
    settings.STRIPE_SUCCESS_URL = (
        "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"
    )


@pytest.fixture(autouse=True)
def _cache_limpia():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def stripe_responde(monkeypatch):
    """Captura los parámetros con los que se crea la sesión, sin salir a la red."""
    pedidos = []

    class _Sesion:
        def __init__(self, n):
            self.id = f"cs_test_nueva{n}"
            self.url = f"https://checkout.stripe.com/c/pay/cs_test_nueva{n}"

    def crear(**params):
        pedidos.append(params)
        return _Sesion(len(pedidos))

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(crear))
    return pedidos


def _post(client, cuerpo=DATOS):
    return client.post(URL, cuerpo, content_type="application/json")


def test_abre_sin_cuenta_y_guarda_carta_y_fila(client, stripe_responde):
    r = _post(client)
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["url"].startswith("https://checkout.stripe.com/")
    fila = PasarelaCheckout.objects.get(checkout_id=cuerpo["checkout_id"])
    assert fila.anonimo and fila.account is None and fila.chart.account is None
    assert fila.codigo_producto == "informe_natal" and fila.url == cuerpo["url"]
    assert fila.nonce_hash == identity.hash_token(cuerpo["nonce"])
    assert cuerpo["nonce"] not in fila.nonce_hash and len(cuerpo["nonce"]) >= 32
    meta = stripe_responde[0]["metadata"]
    assert "account_id" not in meta and meta["chart_id"] == str(fila.chart.pk)


def test_cada_apertura_tiene_su_propio_nonce(client, stripe_responde):
    assert _post(client).json()["nonce"] != _post(client).json()["nonce"]


def test_pide_la_casilla_de_terminos(client, stripe_responde):
    _post(client)
    assert stripe_responde[0]["consent_collection"] == {"terms_of_service": "required"}


def test_idioma_fuera_de_la_lista_blanca_cae_al_por_defecto(client, stripe_responde):
    _post(client, {**DATOS, "locale": "../../x"})
    fila = PasarelaCheckout.objects.get()
    assert fila.locale == stripe_client.LOCALE_POR_DEFECTO


def test_cupon_parcial_viaja_como_descuento(client, stripe_responde):
    Cupon.objects.create(
        codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=10,
        stripe_promotion_code_id="promo_x",
    )
    r = _post(client, {**DATOS, "cupon": "PROMO30"})
    assert r.status_code == 200
    assert stripe_responde[0]["discounts"] == [{"promotion_code": "promo_x"}]
    fila = PasarelaCheckout.objects.get()
    assert fila.cupon.codigo == "PROMO30" and fila.descuento_centavos > 0


def test_cupon_inexistente_es_400_y_no_crea_nada(client, stripe_responde):
    r = _post(client, {**DATOS, "cupon": "NOEXISTE"})
    assert r.status_code == 400 and r.json()["motivo"]
    assert not Chart.objects.exists() and not PasarelaCheckout.objects.exists()


def test_cupon_del_100_no_se_admite_sin_cuenta(client, stripe_responde, cupon_100):
    r = _post(client, {**DATOS, "cupon": cupon_100.codigo})
    assert r.status_code == 400 and r.json()["motivo"] == "requiere_cuenta"
    assert not Chart.objects.exists() and not PasarelaCheckout.objects.exists()
    assert stripe_responde == []


def test_datos_de_nacimiento_invalidos_son_400_y_no_crean_nada(client, stripe_responde):
    r = _post(client, {**DATOS, "date": "no-es-fecha"})
    assert r.status_code == 400
    r = _post(client, {k: v for k, v in DATOS.items() if k != "lat"})
    assert r.status_code == 400
    assert not Chart.objects.exists() and not PasarelaCheckout.objects.exists()
    assert stripe_responde == []


def test_en_mantenimiento_no_crea_nada(client, stripe_responde, monkeypatch):
    monkeypatch.setattr(mantenimiento, "activo", lambda: True)
    assert _post(client).status_code == 503
    assert not Chart.objects.exists() and stripe_responde == []


def test_sin_clave_de_tombstone_no_abre(client, stripe_responde, monkeypatch):
    monkeypatch.setattr("api.compra_anonima.tombstone_hmac_configurada", lambda: False)
    assert _post(client).status_code == 503
    assert not Chart.objects.exists() and stripe_responde == []


def test_stripe_sin_configurar_es_503_y_no_deja_carta(client, settings):
    settings.STRIPE_SECRET_KEY = ""
    assert _post(client).status_code == 503
    assert not Chart.objects.exists() and not PasarelaCheckout.objects.exists()


def test_stripe_caido_es_502_y_no_deja_carta(client, monkeypatch):
    def falla(**p):
        raise stripe_client.stripe.APIConnectionError("sin red")

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(falla))
    assert _post(client).status_code == 502
    assert not Chart.objects.exists() and not PasarelaCheckout.objects.exists()


def test_throttle_propio(client, stripe_responde, monkeypatch):
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"checkout_anonimo": "1/day"},
    )
    assert _post(client).status_code == 200
    assert _post(client).status_code == 429


def test_la_tasa_del_throttle_esta_configurada():
    from django.conf import settings

    assert "checkout_anonimo" in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
