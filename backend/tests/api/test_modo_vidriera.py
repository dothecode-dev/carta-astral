"""Modo vidriera: el sitio como muestra de trabajo, sin cobro ni cuentas.

Con `MODO_VIDRIERA=1` sólo queda viva la parte que no cobra, no guarda datos
de nadie y no gasta en el modelo: calcular una carta, el cielo de hoy, el
buscador de lugares, el catálogo y los conteos. Todo lo demás responde 404.

La regla es una lista de lo que queda ABIERTO, no de lo que se cierra: una
ruta nueva que nadie clasificó queda cerrada en la vidriera, que es el error
barato. Apagado (el default), nada cambia.
"""
import pytest
from django.core.checks import run_checks

from api import urls, vidriera

# Lo que cobra, crea una sesión o recibe plata de una pasarela. La lista de
# abajo no es la regla (la regla es `vidriera.ABIERTAS`): es la superficie
# crítica nombrada una por una, para que cerrarla no dependa de un descuido.
CRITICAS = [
    ("post", "/api/checkout/"),
    ("post", "/api/checkout/anonimo/"),
    ("post", "/api/checkout/anonimo/canjear/"),
    ("get", "/api/checkout/cs_test_123/"),
    ("get", "/api/compras/"),
    ("get", "/api/cupones/CATA100/"),
    ("post", "/api/arrepentimiento/"),
    ("post", "/api/webhooks/stripe/"),
    ("post", "/api/webhooks/mercadopago/"),
    ("post", "/api/webhooks/resend/"),
    ("post", "/api/webhooks/revenuecat"),
    ("post", "/api/auth/google"),
    ("post", "/api/auth/apple"),
    ("post", "/api/auth/email/codigo"),
    ("post", "/api/auth/email"),
    ("post", "/api/auth/logout"),
    ("get", "/api/account/"),
    ("delete", "/api/account/"),
    ("get", "/api/charts/"),
    ("post", "/api/charts/"),
    ("post", "/api/lectura-anonima/"),
]


def _pedir(client, metodo, ruta):
    # Un GET no lleva cuerpo: el cliente de Django lo trataría como query.
    if metodo == "get":
        return client.get(ruta)
    return getattr(client, metodo)(ruta, data="{}", content_type="application/json")


@pytest.mark.django_db
@pytest.mark.parametrize(("metodo", "ruta"), CRITICAS)
def test_en_vidriera_la_superficie_critica_responde_404(client, settings, metodo, ruta):
    settings.MODO_VIDRIERA = True

    resp = _pedir(client, metodo, ruta)

    assert resp.status_code == 404
    assert resp.json()["code"] == "vidriera"


@pytest.mark.django_db
@pytest.mark.parametrize(("metodo", "ruta"), CRITICAS)
def test_apagada_la_vidriera_esas_rutas_siguen_vivas(client, metodo, ruta):
    """Sin el flag, la guarda no existe: lo que responda cada vista (400, 401,
    403…) es cosa suya, pero nunca el 404 de la vidriera."""
    resp = _pedir(client, metodo, ruta)

    assert not (
        resp.status_code == 404
        and resp.headers.get("Content-Type", "").startswith("application/json")
        and resp.json().get("code") == "vidriera"
    )


def test_el_flag_viene_apagado(settings):
    assert settings.MODO_VIDRIERA is False


def test_toda_ruta_esta_cerrada_salvo_las_abiertas():
    """Estructural: cada ruta de `api/urls.py` o está en `ABIERTAS` o pasa por
    la guarda. Una ruta nueva queda cerrada sin que nadie se acuerde."""
    rutas = {str(p.pattern) for p in urls.urlpatterns}
    assert vidriera.ABIERTAS <= rutas, "ABIERTAS nombra rutas que ya no existen"

    for patron in urls.urlpatterns:
        guardada = getattr(patron.callback, "cerrada_en_vidriera", False)
        assert guardada == (str(patron.pattern) not in vidriera.ABIERTAS), str(patron.pattern)


def test_lo_abierto_no_incluye_nada_critico():
    """Lo que queda abierto es una lista corta y a la vista. Si alguien suma
    una ruta de cobro o de login, este test lo obliga a decirlo acá."""
    assert vidriera.ABIERTAS == {
        "catalogo/", "moneda/", "charts/preview/", "geocode/", "sky/", "sky/moon/",
        "estado/", "conteo/teaser/", "conteo/visita/", "vinculo/", "vinculo/preview/",
    }


@pytest.mark.django_db
def test_en_vidriera_el_estado_lo_dice(client, settings):
    """La web no tiene flag propio: le pregunta a `/api/estado/`."""
    assert client.get("/api/estado/").json()["vidriera"] is False

    settings.MODO_VIDRIERA = True

    resp = client.get("/api/estado/")
    assert resp.status_code == 200
    assert resp.json()["vidriera"] is True


@pytest.mark.django_db
def test_en_vidriera_se_sigue_calculando_una_carta(client, settings):
    settings.MODO_VIDRIERA = True

    resp = client.post(
        "/api/charts/preview/",
        data={
            "name": "Demo", "birth_date": "1990-05-17", "birth_time": "14:30",
            "time_known": True, "lat": -34.6037, "lng": -58.3816,
            "tz": "America/Argentina/Buenos_Aires", "place_name": "Buenos Aires",
        },
        content_type="application/json",
    )

    assert resp.status_code != 404
    assert resp.json().get("code") != "vidriera"


def test_en_vidriera_los_checks_de_cobro_no_avisan(settings, monkeypatch):
    """Sin cobro no hay Product de Stripe ni credenciales de Mercado Pago que
    reclamar: el arranque no manda avisos por algo apagado a propósito."""
    settings.MODO_VIDRIERA = True
    settings.STRIPE_PRODUCTOS = {}
    settings.COBRO_ARS_ENABLED = True
    settings.MP_ACCESS_TOKEN = ""
    monkeypatch.setenv("AVISAR_CHECKS", "1")
    avisados = []
    monkeypatch.setattr("api.avisos.avisar_admin", avisados.append)

    encontrados = run_checks(tags=["stripe", "mercadopago"])

    assert encontrados == []
    assert avisados == []
