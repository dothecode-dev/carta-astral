"""Forma exacta de las respuestas que consume la app.

Sólo 2 endpoints verificaban su shape. El resto se testeaba por valores
sueltos, así que un campo que desapareciera del JSON no rompía ningún test —
rompía la app, en el teléfono del usuario, sin aviso previo.

Estos tests afirman el CONJUNTO de claves. Si alguien agrega un campo, el test
falla y hay que actualizarlo a propósito; eso es deliberado: obliga a mirar si
la app lo necesita.
"""

import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.models import Account
from api.sso import VerifiedIdentity

CLAVES_CHART = {
    "id", "house_system", "zodiac", "data", "engine_version",
    "interpretation_langs", "birth",
}
CLAVES_BIRTH = {
    "name", "date", "time", "time_known", "lat", "lng", "tz_name", "place_label",
}


@pytest.fixture
def cliente_con_carta(db, make_account):
    from api.chart_service import create_chart

    acc = make_account()
    chart = create_chart(
        {
            "name": "Ceci",
            "date": "1993-03-21",
            "time": "08:45",
            "time_known": True,
            "lat": -34.6,
            "lng": -58.4,
            "place_label": "Buenos Aires",
        },
        acc,
    )
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    c.account = acc
    c.chart = chart
    return c


@pytest.mark.django_db
def test_el_detalle_de_carta_tiene_exactamente_estas_claves(cliente_con_carta):
    """`_chart_repr` es el objeto más grande de la API y el que arma toda la
    pantalla de la carta en la app."""
    r = cliente_con_carta.get(f"/api/charts/{cliente_con_carta.chart.uuid}/")

    assert r.status_code == 200
    assert set(r.data) == CLAVES_CHART
    assert set(r.data["birth"]) == CLAVES_BIRTH


@pytest.mark.django_db
def test_el_listado_de_cartas_usa_la_misma_forma(cliente_con_carta):
    """Si el listado y el detalle divergen, la app rompe al navegar entre uno
    y otro (le pasó con interpretation_langs)."""
    r = cliente_con_carta.get("/api/charts/")

    assert set(r.data) == {"results"}
    assert set(r.data["results"][0]) == CLAVES_CHART


@pytest.mark.django_db
def test_interpretation_langs_es_una_lista_incluso_sin_lecturas(cliente_con_carta):
    """La app hace `.includes(...)` y `.length` sobre esto: si viniera null,
    la pantalla de la carta explota."""
    r = cliente_con_carta.get(f"/api/charts/{cliente_con_carta.chart.uuid}/")

    assert r.data["interpretation_langs"] == []


@pytest.mark.django_db
def test_la_respuesta_del_login_tiene_exactamente_estas_claves(monkeypatch, settings):
    """Es lo que la app guarda como sesión: si falta account_id, no puede
    identificar a nadie ni configurar RevenueCat."""
    # Apagado por defecto sin app (ver `test_modo_web.py`).
    settings.APP_AUTH_ENABLED = True
    settings.APPLE_AUD = "com.cartaastral.app"
    import api.views as views

    monkeypatch.setattr(
        views, "validate_apple",
        lambda id_token, nonce=None: VerifiedIdentity("apple", "S1", "u@x.com", True),
    )

    r = APIClient().post("/api/auth/apple", {"id_token": "tok"}, format="json")

    assert r.status_code == 200
    assert set(r.data) == {"token", "credits_available", "account_id"}
    assert isinstance(r.data["account_id"], int)
    assert isinstance(r.data["credits_available"], int)


@pytest.mark.django_db
def test_la_cuenta_tiene_exactamente_estas_claves(make_account):
    acc = make_account()
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")

    r = c.get("/api/account/")

    assert set(r.data) == {"credits_available", "account_id"}


@pytest.mark.django_db
def test_el_webhook_responde_con_status(cfg_webhook):
    """RevenueCat sólo mira el código HTTP, pero el body es lo que se lee en
    los logs cuando algo no cuadra."""
    r = APIClient().post(
        "/api/webhooks/revenuecat",
        {"event": {"type": "DESCONOCIDO", "id": "e1", "app_user_id": "999"}},
        format="json",
        HTTP_AUTHORIZATION="secret-abc",
    )

    assert r.status_code == 200
    assert set(r.data) == {"status"}


@pytest.fixture
def cfg_webhook(settings):
    # Apagado por defecto sin app (ver `test_modo_web.py`).
    settings.IAP_WEBHOOK_ENABLED = True
    settings.REVENUECAT_WEBHOOK_AUTH = "secret-abc"
    settings.REVENUECAT_PRODUCT_CREDITS = {"credits_10": 10}
    return settings


@pytest.mark.django_db
def test_healthz_responde_sin_tocar_la_base():
    """Es el liveness de Coolify: si se rompe, el deploy queda marcado
    unhealthy y el contenedor se reinicia en loop. No tenía test."""
    r = APIClient().get("/healthz/")

    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.django_db
def test_healthz_no_pide_autenticacion():
    """Coolify pega sin credenciales: si algún día se aplicara el permiso por
    defecto de DRF, el healthcheck empezaría a dar 401 y el deploy no
    levantaría nunca."""
    r = APIClient().get("/healthz/")

    assert r.status_code != 401
    assert Account.objects.count() == 0  # no crea nada de paso
