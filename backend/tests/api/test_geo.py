"""La moneda inicial sale de la IP (RF2). Sin base, sin IP o con IP privada:
`usd`, nunca un error."""

import pytest
from geoip2.errors import AddressNotFoundError

from api import geo


class _Lector:
    """Lo mínimo de `geoip2.database.Reader` que usa `geo`."""

    def __init__(self, paises: dict[str, str]):
        self.paises = paises

    def country(self, ip):
        try:
            iso = self.paises[ip]
        except KeyError:
            raise AddressNotFoundError(ip) from None

        class _R:
            class country:  # noqa: N801 — imita el objeto de geoip2
                iso_code = iso

        return _R()


@pytest.fixture
def base(monkeypatch):
    monkeypatch.setattr(geo, "_lector", lambda: _Lector({"200.1.2.3": "BR", "8.8.8.8": "US"}))


def test_brasil_es_brl_y_el_resto_usd(base):
    assert geo.pais_de("200.1.2.3") == "BR"
    assert geo.moneda_para("BR") == "brl"
    assert geo.moneda_para("US") == "usd"
    assert geo.moneda_para(None) == "usd"


def test_una_ip_que_la_base_no_conoce_es_usd(base):
    assert geo.pais_de("203.0.113.9") is None


@pytest.mark.parametrize("ip", [None, "", "127.0.0.1", "10.0.0.5", "::1", "no-es-ip"])
def test_sin_ip_o_privada_no_se_consulta(base, ip):
    assert geo.pais_de(ip) is None


def test_sin_base_todo_es_usd(monkeypatch, caplog):
    monkeypatch.setattr(geo, "_lector", lambda: None)

    assert geo.pais_de("200.1.2.3") is None


def test_el_endpoint_toma_la_ultima_ip_del_forwarded_for(client, base):
    """EC6: la primera entrada la escribe el cliente; la última, Traefik."""
    r = client.get("/api/moneda/", HTTP_X_FORWARDED_FOR="8.8.8.8, 200.1.2.3")

    assert r.status_code == 200
    assert r.json() == {"moneda": "brl", "pais": "BR"}


def test_el_endpoint_sin_header_es_usd(client, base):
    assert client.get("/api/moneda/").json() == {"moneda": "usd", "pais": None}


def test_el_checkout_sin_moneda_usa_la_de_la_ip(account_client, base, settings, monkeypatch):
    from api import stripe_client
    from api.models import PasarelaCheckout

    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"

    class _S:
        id = "cs_geo"
        url = "https://checkout.stripe.com/c/pay/cs_geo"

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **k: _S()))

    account_client.post("/api/checkout/", {"producto": "informe_natal"}, HTTP_X_FORWARDED_FOR="200.1.2.3")

    assert PasarelaCheckout.objects.get(checkout_id="cs_geo").moneda == "brl"


def test_el_checkout_desde_brasil_puede_pedir_usd(account_client, base, settings, monkeypatch):
    """R2: el turista en Brasil paga en dólares."""
    from api import stripe_client
    from api.models import PasarelaCheckout

    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    settings.STRIPE_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_SESSION_ID}"

    class _S:
        id = "cs_geo2"
        url = "u"

    monkeypatch.setattr(stripe_client.stripe.checkout.Session, "create", staticmethod(lambda **k: _S()))

    account_client.post("/api/checkout/", {"producto": "informe_natal", "moneda": "usd"}, HTTP_X_FORWARDED_FOR="200.1.2.3")

    assert PasarelaCheckout.objects.get(checkout_id="cs_geo2").moneda == "usd"
