"""El cliente de Polar: a dónde le pega y qué le manda.

Polar es merchant of record: se le crea una sesión de checkout desde el backend
y él cobra, factura y liquida impuestos. Este módulo es sólo el que habla con
su API — quién puede comprar y qué se hace con el pago viven en la vista y en
el webhook.

El sandbox es **otra organización**, con su propia cuenta, sus productos y su
token: apuntar al entorno equivocado no falla con un error claro, cobra de
verdad o no cobra nada.
"""

import json

import httpx
import pytest

from api import polar

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.POLAR_ACCESS_TOKEN = "polar_at_de_prueba"
    settings.POLAR_ENVIRONMENT = "sandbox"
    settings.POLAR_SUCCESS_URL = "https://astraguia.com/es/compra"
    settings.POLAR_PRODUCTOS = {
        "prod_uno": "informe_natal",
        "prod_tres": "pack_3_natal",
        "prod_cinco": "pack_5_natal",
    }


@pytest.fixture
def polar_responde(monkeypatch):
    """Reemplaza el transporte HTTP, no la función: así el test ejercita el
    armado del request de verdad —URL, headers, body— en vez de comprobar que
    un mock fue llamado."""
    pedidos = []

    def _armar(status=201, body=None):
        def handler(request: httpx.Request) -> httpx.Response:
            pedidos.append(request)
            return httpx.Response(
                status, json=body or {"id": "chk_1", "url": "https://polar.sh/pay/chk_1"}
            )

        monkeypatch.setattr(
            polar, "_client",
            lambda: httpx.Client(transport=httpx.MockTransport(handler), timeout=polar.TIMEOUT),
        )
        return pedidos

    return _armar


def test_apunta_al_sandbox_cuando_el_entorno_lo_dice(settings):
    settings.POLAR_ENVIRONMENT = "sandbox"
    assert polar.base_url() == "https://sandbox-api.polar.sh/v1"


def test_apunta_a_produccion_en_cualquier_otro_caso(settings):
    """El default es producción: un entorno mal escrito no puede dejar los
    pagos reales entrando por el sandbox, que no cobra."""
    settings.POLAR_ENVIRONMENT = ""
    assert polar.base_url() == "https://api.polar.sh/v1"


def test_el_checkout_manda_el_producto_pedido_y_la_cuenta(polar_responde, make_account):
    pedidos = polar_responde()
    cuenta = make_account()

    checkout_id, url = polar.crear_checkout(cuenta, "pack_3_natal")

    enviado = json.loads(pedidos[0].content)
    assert enviado["products"] == ["prod_tres"]
    assert enviado["metadata"]["account_id"] == str(cuenta.pk)
    assert (checkout_id, url) == ("chk_1", "https://polar.sh/pay/chk_1")


def test_el_checkout_va_firmado_con_el_token(polar_responde, make_account):
    pedidos = polar_responde()

    polar.crear_checkout(make_account(), "informe_natal")

    assert pedidos[0].headers["authorization"] == "Bearer polar_at_de_prueba"
    assert str(pedidos[0].url).startswith("https://sandbox-api.polar.sh/v1/checkouts/")


def test_la_carta_viaja_en_la_metadata_cuando_se_compra_desde_una(
    polar_responde, make_account, make_chart,
):
    """El webhook la necesita para arrancar el informe apenas entra la plata.
    Va como respaldo de `PolarCheckout`, que es quien la guarda de este lado."""
    pedidos = polar_responde()
    cuenta = make_account()
    carta = make_chart(account=cuenta)

    polar.crear_checkout(cuenta, "informe_natal", chart=carta)

    assert json.loads(pedidos[0].content)["metadata"]["chart_id"] == str(carta.pk)


def test_un_producto_que_no_esta_en_el_catalogo_no_abre_checkout(make_account):
    with pytest.raises(KeyError):
        polar.crear_checkout(make_account(), "producto_inventado")


def test_un_producto_del_catalogo_sin_ficha_en_polar_no_abre_checkout(
    settings, make_account,
):
    """El catálogo y Polar son dos listas que hay que mantener alineadas. Si
    una falta, mejor fallar acá que abrir un checkout que el webhook después no
    va a saber acreditar."""
    settings.POLAR_PRODUCTOS = {"prod_uno": "informe_natal"}

    with pytest.raises(polar.PolarNoConfigurado):
        polar.crear_checkout(make_account(), "pack_5_natal")


def test_un_producto_gratis_no_se_cobra(make_account):
    """`lectura_breve` vale 0: un checkout de US$ 0 deja una orden que el
    webhook no sabe validar."""
    with pytest.raises(ValueError):
        polar.crear_checkout(make_account(), "lectura_breve")


def test_sin_token_no_intenta_cobrar(settings, make_account):
    """Fail-closed: sin credencial no se abre un checkout que después nadie
    puede acreditar."""
    settings.POLAR_ACCESS_TOKEN = ""

    with pytest.raises(polar.PolarNoConfigurado):
        polar.crear_checkout(make_account(), "informe_natal")


def test_si_polar_falla_lo_dice_con_su_propia_excepcion(polar_responde, make_account):
    """Un 500 de Polar no puede subir como un error genérico: la vista tiene
    que poder distinguirlo para responder 502 y no dejar basura."""
    polar_responde(status=500, body={"detail": "boom"})

    with pytest.raises(polar.PolarError):
        polar.crear_checkout(make_account(), "informe_natal")


def test_traduce_el_id_de_polar_al_codigo_del_catalogo():
    assert polar.codigo_de_producto("prod_cinco") == "pack_5_natal"


def test_un_id_de_polar_desconocido_no_se_traduce():
    """Lo usa el webhook: una orden de un producto que no mapeamos se descarta
    en vez de acreditar cualquier cosa."""
    with pytest.raises(KeyError):
        polar.codigo_de_producto("prod_que_no_conocemos")


def test_el_pedido_lleva_timeout():
    """Un checkout colgado bloquea un worker de gunicorn; con --timeout 60, el
    arbiter termina matándolo."""
    assert polar.TIMEOUT is not None


def test_la_url_de_retorno_lleva_el_idioma_de_quien_compra(polar_responde, make_account, settings):
    """Quien compra navegando en inglés tiene que volver a una página en
    inglés. `POLAR_SUCCESS_URL` es una plantilla con `{locale}` justamente
    porque el idioma lo sabe el navegador, no la configuración."""
    settings.POLAR_SUCCESS_URL = "https://astraguia.com/{locale}/compra"
    pedidos = polar_responde()

    polar.crear_checkout(make_account(), "informe_natal", locale="en")

    assert json.loads(pedidos[0].content)["success_url"] == "https://astraguia.com/en/compra"


def test_el_placeholder_de_polar_llega_intacto(polar_responde, make_account, settings):
    """`{CHECKOUT_ID}` lo reemplaza Polar, no nosotros.

    La página de retorno lo necesita para saber qué compra seguir: sin él no
    puede distinguir a quién acaba de pagar de alguien que entró de casualidad.
    Sólo `{locale}` se reemplaza de este lado, así que un reemplazo más goloso
    —un `format()`, por ejemplo— rompería la URL entera.
    """
    settings.POLAR_SUCCESS_URL = "https://astraguia.com/{locale}/compra?checkout_id={CHECKOUT_ID}"
    pedidos = polar_responde()

    polar.crear_checkout(make_account(), "informe_natal", locale="pt")

    assert json.loads(pedidos[0].content)["success_url"] == (
        "https://astraguia.com/pt/compra?checkout_id={CHECKOUT_ID}"
    )


def test_un_idioma_que_no_existe_no_arma_la_url_de_retorno(polar_responde, make_account, settings):
    """Lista blanca, no concatenación: el locale llega del navegador y va a
    parar a una URL de retorno. Sin esta guarda, cualquiera podría fabricar el
    destino al que Polar devuelve a la persona después de pagar."""
    settings.POLAR_SUCCESS_URL = "https://astraguia.com/{locale}/compra"
    pedidos = polar_responde()

    polar.crear_checkout(make_account(), "informe_natal", locale="../evil.com")

    enviado = json.loads(pedidos[0].content)
    assert enviado["success_url"] == "https://astraguia.com/es/compra"
