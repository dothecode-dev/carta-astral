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
    # Review 07-10, punto 1: la segunda compra cayó en una cuenta sin
    # verificar que no creó, así que el nonce de la primera ya no abre sesión
    # —por el paso 1 o por la carrera de `resolver_cuenta`, da igual—.
    creadora = next(f for f in filas if f.cuenta_nueva)
    assert creadora.canjeado_at is not None


# --- Volver de Stripe (Task 6, RF11): dos canjes a la vez, una sola sesión ---


@requiere_postgres
def test_canjes_simultaneos_con_el_nonce_abren_una_sola_sesion(anonima, make_account):
    from django.utils import timezone

    from api import compra_anonima
    from api.identity import hash_token
    from api.models import Session

    cuenta = make_account(email="c2@mail.com")
    anonima.account, anonima.cuenta_nueva = cuenta, True
    anonima.acreditado_at = timezone.now()
    anonima.nonce_hash = hash_token("n0nce")
    anonima.save()

    resultados, errores = en_hilos(lambda _i: compra_anonima.canjear(SESSION_ANONIMA, "n0nce"), 3)

    assert not errores, f"un error inesperado rompió el canje: {errores}"
    assert sorted(r["estado"] for r in resultados) == ["invalido", "invalido", "sesion"]
    assert Session.objects.filter(account=cuenta).count() == 1


# --- Review 07-10, punto 1: canje del atacante ↔ compra de la dueña, a la vez ---


@requiere_postgres
def test_el_canje_y_una_segunda_compra_a_la_vez_no_dejan_sesion_ni_se_traban(make_chart):
    """El atacante canjea su nonce de la primera compra justo cuando el
    webhook adjudica la compra de la dueña a la misma cuenta sin verificar.
    Gane quien gane el lock, al final no queda ninguna sesión en la cuenta
    (o la adjudicación borra la que abrió el canje, o el canje encuentra el
    nonce gastado), y no hay deadlock: los dos caminos lockean filas de
    checkout antes que la cuenta. Se repite para cubrir los dos órdenes."""
    from django.utils import timezone

    from api import compra_anonima
    from api.identity import hash_token
    from api.models import Session

    for vuelta in range(6):
        email = f"carrera{vuelta}@mail.com"
        atacante, victima = f"cs_test_atac_{vuelta}", f"cs_test_vict_{vuelta}"
        for checkout_id in (atacante, victima):
            PasarelaCheckout.objects.create(
                checkout_id=checkout_id, account=None, codigo_producto="informe_natal",
                chart=make_chart(account=None), anonimo=True, nonce_hash=hash_token(f"n-{checkout_id}"),
                precio_centavos=2900,
            )
        cuenta = compra_anonima.adjudicar(atacante, email)
        PasarelaCheckout.objects.filter(checkout_id=atacante).update(acreditado_at=timezone.now())

        def paso(i, atacante=atacante, victima=victima, email=email):
            if i == 0:
                return compra_anonima.canjear(atacante, f"n-{atacante}")
            return compra_anonima.adjudicar(victima, email)

        _, errores = en_hilos(paso, 2)

        assert not errores, f"vuelta {vuelta}: {errores}"
        assert PasarelaCheckout.objects.get(checkout_id=victima).account == cuenta
        assert not Session.objects.filter(account=cuenta).exists(), f"vuelta {vuelta}"
