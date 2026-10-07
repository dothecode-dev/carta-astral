"""Concurrencia real de la adjudicación anónima (RF6). Superficie de PLATA e
IDENTIDAD.

Stripe puede entregar el mismo evento dos veces a la vez, y `completed` con
`async_payment_succeeded` de la misma sesión también: tienen que crear a lo
sumo una cuenta, acreditar una vez y asignar la carta una vez. Sólo valen
contra Postgres: en SQLite `SELECT ... FOR UPDATE` se ignora.
"""

import json

import pytest
from django.test import Client

from api import webhooks_stripe
from api.models import Account, Chart, Interpretation, Movimiento, PasarelaCheckout
from tests.api.concurrencia import en_hilos, requiere_postgres
from tests.api.conftest import PRECIO_ANONIMA, SESSION_ANONIMA, con_mail
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {PRECIO_ANONIMA: "informe_natal"}


@requiere_postgres
def test_tres_entregas_simultaneas_crean_una_cuenta_y_acreditan_una_vez(monkeypatch, anonima, sin_hilo):
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _id: con_mail("c@mail.com"))

    _, errores = en_hilos(lambda _i: webhooks_stripe._acreditar(SESSION_ANONIMA), 3)

    assert not errores, f"un error inesperado rompió la entrega: {errores}"
    assert Account.objects.filter(email="c@mail.com").count() == 1
    cuenta = Account.objects.get(email="c@mail.com")
    anonima.refresh_from_db()
    assert anonima.account == cuenta and anonima.cuenta_nueva is True
    assert Chart.objects.get(pk=anonima.chart_id).account == cuenta
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}").count() == 1
    assert Interpretation.objects.filter(chart_id=anonima.chart_id).count() == 1


@requiere_postgres
def test_completed_y_async_a_la_vez_crean_una_cuenta_y_acreditan_una_vez(monkeypatch, anonima, sin_hilo):
    """Por la vista, con los dos tipos de evento de verdad."""
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _id: con_mail("ca@mail.com"))
    tipos = ["checkout.session.completed", "checkout.session.async_payment_succeeded"]

    def entregar(i):
        cuerpo = json.dumps({
            "id": f"evt_{i}", "type": tipos[i],
            "data": {"object": {"id": SESSION_ANONIMA, "object": "checkout.session"}},
        }).encode()
        return Client().post(
            "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
        ).status_code

    estados, errores = en_hilos(entregar, 2)

    assert not errores, f"un error inesperado rompió la entrega: {errores}"
    assert sorted(estados) == [200, 200]
    assert Account.objects.filter(email="ca@mail.com").count() == 1
    anonima.refresh_from_db()
    assert anonima.cuenta_nueva is True and anonima.acreditado_at is not None
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION_ANONIMA}").count() == 1


@requiere_postgres
def test_dos_compras_distintas_con_el_mismo_mail_nuevo_crean_una_cuenta_y_una_sola_es_nueva(
    monkeypatch, make_chart, sin_hilo,
):
    """Dos checkouts anónimos distintos, pagados con el mismo mail que todavía
    no tiene cuenta. Cada uno toma el lock de SU fila, así que no se
    serializan ahí: la carrera la resuelve la unicidad de
    `ProviderIdentity(email, sub)`. Quien la pierde se lleva la cuenta del
    otro, y para él esa cuenta ya existía: NO puede salir `cuenta_nueva`, o
    su navegador entraría a una cuenta que no creó su compra."""
    ids = ["cs_test_par_0", "cs_test_par_1"]
    for checkout_id in ids:
        PasarelaCheckout.objects.create(
            checkout_id=checkout_id, account=None, codigo_producto="informe_natal",
            chart=make_chart(account=None), anonimo=True, nonce_hash="y" * 64,
            precio_centavos=2900,
        )
    monkeypatch.setattr(
        webhooks_stripe, "obtener_sesion",
        lambda sid: {**con_mail("par@mail.com"), "id": sid, "payment_intent": f"pi_{sid}"},
    )

    _, errores = en_hilos(lambda i: webhooks_stripe._acreditar(ids[i]), 2)

    assert not errores, f"un error inesperado rompió la entrega: {errores}"
    assert Account.objects.filter(email="par@mail.com").count() == 1
    cuenta = Account.objects.get(email="par@mail.com")
    filas = list(PasarelaCheckout.objects.filter(checkout_id__in=ids))
    assert all(f.account == cuenta and f.acreditado_at is not None for f in filas)
    assert sorted(f.cuenta_nueva for f in filas) == [False, True]
