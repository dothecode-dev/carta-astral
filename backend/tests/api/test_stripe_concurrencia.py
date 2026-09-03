"""Concurrencia real sobre el webhook de Stripe. Superficie de PLATA.

Tests 33 y 35 de la spec. Los ocho de `test_canje_concurrencia.py` ejercitan el
canje; estos ejercitan el webhook entero, que es lo que sale a producción y lo
que Stripe puede entregar dos veces a la vez —reintenta si no recibe el 200 a
tiempo, y el reembolso puede pisarse con el pago que lo precede—.

Sólo corren contra Postgres: en SQLite `SELECT ... FOR UPDATE` se ignora.
"""

import pytest

from api import interpretation_service as svc
from api import webhooks_stripe
from api.models import Derecho, Interpretation, Movimiento, PasarelaCheckout
from tests.api.concurrencia import en_hilos, requiere_postgres

SESSION = "cs_test_carrera"
PI = "pi_carrera"


@pytest.fixture(autouse=True)
def _configurado(settings, monkeypatch):
    settings.STRIPE_WEBHOOK_SECRET = "whsec_" + "z" * 32
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: {
        "id": SESSION, "payment_status": "paid",
        "amount_subtotal": 2900, "amount_total": 2900,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": PI, "metadata": {},
        "line_items": {"data": [{"price": {"id": "price_natal"}, "quantity": 1}]},
    })


@pytest.fixture
def sin_hilo(monkeypatch):
    arrancados = []
    monkeypatch.setattr(
        svc, "arrancar_en_hilo",
        lambda interpretacion, chart, account: arrancados.append(interpretacion),
    )
    return arrancados


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_dos_entregas_simultaneas_acreditan_y_arrancan_una_sola_vez(
    make_account, make_chart, sin_hilo,
):
    """La entrega duplicada del mismo evento: Stripe reintenta si no recibe el
    200 a tiempo, y las dos pueden estar adentro a la vez."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal", chart=carta,
    )

    _resultados, errores = en_hilos(lambda _i: webhooks_stripe._acreditar(SESSION), 3)

    assert not errores, f"un error inesperado rompió la entrega: {errores}"
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1
    assert Interpretation.objects.filter(chart=carta).count() == 1
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_el_reembolso_y_el_pago_a_la_vez_no_se_pierden(make_account, make_chart, sin_hilo):
    """El reembolso no puede descartarse como duplicado del pago —por eso los
    `external_id` llevan prefijos distintos— ni desaparecer en silencio: si
    llega antes de que el pago haya guardado el `payment_intent`, tiene que
    salir por `ReembolsoSinCompra`, que es un 5xx y un reintento."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal", chart=carta,
    )
    refund = {"id": "re_carrera", "amount": 2900, "payment_intent": PI}

    def operar(i):
        if i == 0:
            return webhooks_stripe._acreditar(SESSION)
        return webhooks_stripe._reembolsar(refund)

    _resultados, errores = en_hilos(operar, 2)

    assert all(
        isinstance(e, webhooks_stripe.ReembolsoSinCompra) for e in errores
    ), f"el reembolso falló por algo que un reintento no arregla: {errores}"
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1

    revocaciones = Movimiento.objects.filter(external_id="stripe:refund:re_carrera")
    if errores:
        # El reembolso llegó antes: no revocó nada, y el 5xx lo trae de vuelta.
        assert not revocaciones.exists()
    else:
        assert revocaciones.count() == 1
        assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
