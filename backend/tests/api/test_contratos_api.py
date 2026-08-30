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
from config.settings import INTERNAL_HOSTS

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


@pytest.fixture
def cliente_sin_free_con_carta(db, make_account):
    """Misma carta que `cliente_con_carta`, pero la cuenta arranca sin
    crédito free: sólo sirve para probar el 402 de la lectura breve."""
    from api.chart_service import create_chart

    acc = make_account(free_balance=0, paid_balance=5)
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


@pytest.fixture
def cliente_sin_paid_con_carta(db, make_account):
    """Contrapunto: cuenta con free pero sin paid, para probar el 402 del
    informe completo."""
    from api.chart_service import create_chart

    acc = make_account(free_balance=5, paid_balance=0)
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
def test_sin_tier_es_400(cliente_con_carta):
    """No se adivina: adivinar el tier es gastar el lote de crédito
    equivocado (la breve cobra free, el informe completo cobra paid) por un
    olvido del cliente."""
    r = cliente_con_carta.post(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/",
        {"lang": "es"},
        format="json",
    )
    assert r.status_code == 400
    assert "tier" in r.json()["error"]


@pytest.mark.django_db
def test_tier_desconocido_es_400(cliente_con_carta):
    """"premium" no es ninguno de los dos productos que vende ASTRA."""
    r = cliente_con_carta.post(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/",
        {"lang": "es", "tier": "premium"},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_el_402_dice_cual_credito_falto_sin_free(cliente_sin_free_con_carta):
    """`QuotaExceeded.lote` viaja hasta la respuesta: la web muestra "te
    quedaste sin lecturas gratis" en vez de "comprá el informe completo"."""
    r = cliente_sin_free_con_carta.post(
        f"/api/charts/{cliente_sin_free_con_carta.chart.uuid}/interpretation/",
        {"lang": "es", "tier": "corto"},
        format="json",
    )
    assert r.status_code == 402
    assert r.json()["code"] == "sin_free"


@pytest.mark.django_db
def test_el_402_dice_cual_credito_falto_sin_paid(cliente_sin_paid_con_carta):
    """Contrapunto: sin crédito paid, pedir el informe completo devuelve
    "sin_paid", no "sin_free" — el `f"sin_{exc.lote}"` de la vista tiene que
    reflejar el lote real, no un literal fijo."""
    r = cliente_sin_paid_con_carta.post(
        f"/api/charts/{cliente_sin_paid_con_carta.chart.uuid}/interpretation/",
        {"lang": "es", "tier": "largo"},
        format="json",
    )
    assert r.status_code == 402
    assert r.json()["code"] == "sin_paid"


@pytest.mark.django_db
def test_post_con_tier_corto_devuelve_202_y_cobra_free(cliente_con_carta, settings):
    """Camino feliz de la breve: hasta ahora sólo estaba probado el 402
    (`test_el_402_dice_cual_credito_falto_sin_free`) — nada verificaba que
    con crédito free disponible el POST aceptara "corto" y cobrara el lote
    correcto. Es el único endpoint de esta tarea que cobra, y el que
    atraparía una regresión si algún día alguien mete una condición por
    tier acá."""
    settings.ANTHROPIC_API_KEY = ""  # el hilo de fondo no debe pegarle a la API real en un test
    cuenta = cliente_con_carta.account
    free_antes, paid_antes = cuenta.free_balance, cuenta.paid_balance

    r = cliente_con_carta.post(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/",
        {"lang": "es", "tier": "corto"},
        format="json",
    )

    assert r.status_code == 202
    cuenta.refresh_from_db()
    assert cuenta.free_balance == free_antes - 1  # cobró del lote free...
    assert cuenta.paid_balance == paid_antes  # ...y no tocó el paid


@pytest.mark.django_db
def test_el_estado_reporta_una_sola_seccion_para_la_breve(cliente_con_carta):
    """La barra de progreso de la lectura breve no puede decir "1 de 8": ese
    catálogo es de una sola sección (`SECCION_BREVE`), no las ocho del
    informe completo."""
    r = cliente_con_carta.get(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/estado/?lang=es&tier=corto"
    )
    assert r.json()["total"] == 1


@pytest.mark.django_db
def test_el_estado_sin_tier_es_400(cliente_con_carta):
    """Sin tier no hay catálogo de secciones que calcular
    (`secciones_aplicables` lo exige): el estado no puede asumir cuál de los
    dos productos está sondeando la web."""
    r = cliente_con_carta.get(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/estado/?lang=es"
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_el_estado_con_tier_desconocido_es_400(cliente_con_carta):
    """Contrapunto de arriba: no sólo ausente, tampoco un valor que no sea
    ninguno de los dos productos."""
    r = cliente_con_carta.get(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/estado/?lang=es&tier=premium"
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_el_get_de_lectura_sin_tier_es_400(cliente_con_carta):
    """Mismo motivo que en el POST: sin tier, el GET no sabe si buscar la
    lectura breve o el informe completo, y devolver cualquiera de los dos
    adivinando sería entregar el producto equivocado."""
    r = cliente_con_carta.get(
        f"/api/charts/{cliente_con_carta.chart.uuid}/interpretation/?lang=es"
    )
    assert r.status_code == 400


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
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1"])
def test_healthz_contesta_al_host_interno_del_contenedor(host, settings):
    """Docker pregunta por `localhost`, no por el dominio público.

    `ALLOWED_HOSTS` se arma con los dominios del entorno, así que un pedido con
    `Host: localhost` moría en 400 antes de llegar a la vista —Django valida el
    host en el middleware— y el healthcheck de Coolify daba la aplicación por
    muerta. Se comprobó contra producción el 13-08-2026: `curl` desde adentro
    del contenedor devolvía 400 mientras el dominio público devolvía 200.
    """
    settings.ALLOWED_HOSTS = ["api.ejemplo.test"] + INTERNAL_HOSTS

    r = APIClient().get("/healthz/", headers={"host": host})

    assert r.status_code == 200


@pytest.mark.django_db
def test_healthz_no_pide_autenticacion():
    """Coolify pega sin credenciales: si algún día se aplicara el permiso por
    defecto de DRF, el healthcheck empezaría a dar 401 y el deploy no
    levantaría nunca."""
    r = APIClient().get("/healthz/")

    assert r.status_code != 401
    assert Account.objects.count() == 0  # no crea nada de paso
