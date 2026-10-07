"""RF5b de punta a punta: cuando la unidad comprada salda una deuda, la
persona se entera y la web no espera un informe que no va a arrancar.

Antes (revisión final de «pagar es entrar», Important 1) el webhook lo
absorbía con un `warning` y nadie lo mostraba: quien pagó se quedaba mirando
la animación de espera. Ahora la fila guarda el hecho (`saldo_deuda`), el
estado del checkout y el canje anónimo lo devuelven, y el log es `error`
para que Sentry avise.
"""

import json
import logging

import pytest
from django.utils import timezone

from api import compra_anonima, notificaciones, webhooks_stripe
from api.identity import hash_token
from api.models import Interpretation, PasarelaCheckout
from tests.api.conftest import SESSION_ANONIMA, con_mail
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("django_cache_cleared")]

NONCE = "n0nce-deuda"


def _sesion(checkout_id):
    return {
        "id": checkout_id, "payment_status": "paid", "amount_subtotal": 2900,
        "amount_total": 2900, "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": f"pi_{checkout_id}", "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    }


@pytest.fixture
def entregar(client, monkeypatch, settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}

    def _entregar(checkout_id):
        sesion = _sesion(checkout_id)
        monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _id: sesion)
        cuerpo = json.dumps({
            "id": f"evt_{checkout_id}", "type": "checkout.session.completed",
            "data": {"object": {"id": checkout_id, "object": "checkout.session"}},
        }).encode()
        return client.post(
            "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
        )

    return _entregar


@pytest.fixture
def enviados(monkeypatch):
    lista = []
    monkeypatch.setattr(
        notificaciones, "enviar_codigo", lambda email, claro, lang: lista.append(email),
    )
    return lista


@pytest.fixture
def account_client(make_account):
    """Una cuenta en blanco con sesión: SIN derechos, a diferencia del
    `account_client` global (que trae 3 informes y canjearía con ellos)."""
    from rest_framework.test import APIClient

    from api.auth import create_session

    acc = make_account(email="deudor@example.com", email_verified=True)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_session(acc)}")
    client.account = acc
    return client


def _con_deuda(cuenta):
    cuenta.deuda = 1
    cuenta.save(update_fields=["deuda"])
    return cuenta


# --- Checkout CON cuenta: la fila guarda el hecho y el estado lo devuelve ----


def test_webhook_con_deuda_marca_la_fila(entregar, account_client, make_chart, sin_hilo):
    cuenta = _con_deuda(account_client.account)
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_deuda", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )

    assert entregar("cs_deuda").status_code == 200

    fila.refresh_from_db()
    assert fila.acreditado_at is not None
    assert fila.saldo_deuda is True
    assert not Interpretation.objects.filter(chart=fila.chart).exists()
    assert sin_hilo == []


def test_el_estado_devuelve_saldo_pendiente(entregar, account_client, make_chart, sin_hilo):
    cuenta = _con_deuda(account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="cs_deuda", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    entregar("cs_deuda")

    cuerpo = account_client.get("/api/checkout/cs_deuda/").json()

    assert cuerpo["estado"] == "acreditado"
    assert cuerpo["saldo_pendiente"] is True


def test_sin_deuda_ni_la_fila_ni_el_estado_lo_dicen(entregar, account_client, make_chart, sin_hilo):
    cuenta = account_client.account
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_ok", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    entregar("cs_ok")

    fila.refresh_from_db()
    assert fila.saldo_deuda is False
    cuerpo = account_client.get("/api/checkout/cs_ok/").json()
    assert cuerpo["estado"] == "acreditado"
    assert "saldo_pendiente" not in cuerpo
    assert len(sin_hilo) == 1


def test_un_reintento_no_borra_la_marca(entregar, account_client, make_chart, sin_hilo):
    """El segundo `completed` sale por el duplicado de `aplicar_compra`: la
    marca quedó en el mismo átomo que el otorgamiento y sigue puesta."""
    cuenta = _con_deuda(account_client.account)
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_deuda", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    entregar("cs_deuda")
    assert entregar("cs_deuda").status_code == 200

    fila.refresh_from_db()
    assert fila.saldo_deuda is True


def test_los_dos_logs_son_error_y_sin_mail(
    entregar, account_client, make_chart, sin_hilo, caplog, monkeypatch,
):
    # `api` no propaga a la raíz (LOGGING): sin esto caplog no ve nada.
    monkeypatch.setattr(logging.getLogger("api"), "propagate", True)
    cuenta = _con_deuda(account_client.account)
    PasarelaCheckout.objects.create(
        checkout_id="cs_deuda", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta),
    )
    with caplog.at_level(logging.WARNING):
        entregar("cs_deuda")

    deuda = [r for r in caplog.records if "deuda" in r.getMessage()]
    assert {r.name for r in deuda} >= {"api.canje", "api.compra_service"}
    assert all(r.levelno == logging.ERROR for r in deuda)
    assert all("cs_deuda" in r.getMessage() and str(cuenta.pk) in r.getMessage() for r in deuda)
    assert not any(cuenta.email in r.getMessage() for r in caplog.records)


# --- Compra SIN cuenta: el canje lo devuelve -----------------------------------


def test_compra_anonima_a_cuenta_con_deuda_el_canje_lo_dice(
    entregar_anonima, anonima, make_account, sin_hilo, enviados,
):
    """Paga sin cuenta con el mail de una cuenta verificada que debe: la
    compra va a esa cuenta, salda la deuda, y el canje (rama del código) lo
    dice además de mandar el código."""
    cuenta = _con_deuda(make_account(email="deudora@example.com", email_verified=True))

    assert entregar_anonima(con_mail("deudora@example.com")).status_code == 200

    anonima.refresh_from_db()
    assert anonima.account_id == cuenta.pk
    assert anonima.saldo_deuda is True
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save(update_fields=["nonce_hash"])

    r = compra_anonima.canjear(SESSION_ANONIMA, NONCE)

    assert r["estado"] == "codigo"
    assert r["saldo_pendiente"] is True


def test_canje_con_sesion_tambien_lo_dice(anonima, make_account):
    cuenta = make_account(email="nueva@example.com", email_verified=False)
    anonima.account, anonima.cuenta_nueva = cuenta, True
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.saldo_deuda = True
    anonima.save()

    r = compra_anonima.canjear(SESSION_ANONIMA, NONCE)

    assert r["estado"] == "sesion"
    assert r["saldo_pendiente"] is True


def test_canje_normal_no_lo_dice(anonima, make_account):
    cuenta = make_account(email="nueva@example.com", email_verified=False)
    anonima.account, anonima.cuenta_nueva = cuenta, True
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save()

    r = compra_anonima.canjear(SESSION_ANONIMA, NONCE)

    assert r["estado"] == "sesion"
    assert "saldo_pendiente" not in r
