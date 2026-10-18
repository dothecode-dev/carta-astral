"""La moneda inicial sale de la IP (RF2). Sin base, sin IP o con IP privada:
`usd`, nunca un error."""

import pytest

from api import geo


class _Lector:
    """Lo mínimo de `maxminddb.Reader` que usa `geo`."""

    def __init__(self, paises: dict[str, str]):
        self.paises = paises

    def get(self, ip):
        iso = self.paises.get(ip)
        return {"country": {"iso_code": iso}} if iso else None


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


def test_el_checkout_sin_moneda_cobra_en_usd_aunque_la_ip_sea_de_brasil(account_client, base, settings, monkeypatch):
    """Se cobra en la moneda que el cliente vio y mandó. La IP sólo sugiere
    qué mostrar (`/api/moneda/`): si decidiera el cobro, una web que muestra
    US$ abriría un pago en reales (decisión del 18-10-2026)."""
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

    assert PasarelaCheckout.objects.get(checkout_id="cs_geo").moneda == "usd"


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


def test_una_base_invalida_no_tumba_nada_y_avisa_una_sola_vez(client, settings, tmp_path, caplog):
    """Un archivo que no es una base (descarga cortada, HTML) es «no sé», no
    un 500, y no se reintenta ni se loguea en cada request."""
    ruta = tmp_path / "x.mmdb"
    ruta.write_bytes(b"no es una base")
    settings.GEOIP_PATH = str(ruta)
    geo.recargar()

    with caplog.at_level("WARNING", logger="api.geo"):
        assert geo.pais_de("200.1.2.3") is None
        r = client.get("/api/moneda/", HTTP_X_FORWARDED_FOR="200.1.2.3")

    assert r.status_code == 200
    assert r.json() == {"moneda": "usd", "pais": None}
    assert len([x for x in caplog.records if "inválida" in x.getMessage()]) == 1

