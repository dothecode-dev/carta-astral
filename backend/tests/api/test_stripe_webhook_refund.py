"""El reembolso de una compra de Stripe: tests 21-25, 40 y 41 de la spec.

Dos cosas que no son obvias y salieron de incidentes:

- **El evento no trae el id de la sesión.** `refund.created` llega con
  `payment_intent` y `charge`, así que la compra se resuelve por el
  `payment_intent` que guardamos al acreditar. Verificado contra un reembolso
  real en modo test.
- **No se le quita a nadie un informe ya entregado.** `canje.revocar` baja el
  derecho hasta donde alcanza y manda el resto a deuda, que se cancela contra
  la próxima compra.
"""

import json

import pytest

from api.canje import aplicar_compra, canjear
from api.models import Account, Derecho, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
PI = "pi_reembolso"
REFUND = "re_1"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal"}


def _entregar(client, refund=None):
    cuerpo = json.dumps({
        "id": "evt_r", "type": "refund.created",
        "data": {"object": refund if refund is not None else _refund()},
    }).encode()
    return client.post(
        URL, data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


def _refund(**cambios) -> dict:
    """La forma exacta que devolvió un `refund.created` real en modo test."""
    refund = {
        "id": REFUND, "object": "refund", "amount": 2900, "currency": "usd",
        "charge": "ch_1", "payment_intent": PI, "reason": None, "status": "succeeded",
    }
    refund.update(cambios)
    return refund


@pytest.fixture
def comprado(make_account, make_chart):
    """Una compra ya acreditada, como la deja el webhook de pago."""
    cuenta = make_account()
    fila = PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=cuenta, codigo_producto="informe_natal",
        chart=make_chart(account=cuenta), payment_intent=PI,
    )
    aplicar_compra(cuenta, "informe_natal", 2900, external_id="stripe:session:cs_1")
    return fila


def test_un_reembolso_revoca_lo_comprado(client, comprado):
    r = _entregar(client)

    assert r.status_code == 200
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(
        tipo="revocacion", external_id=f"stripe:refund:{REFUND}",
    ).count() == 1


def test_reembolsar_algo_ya_usado_deja_deuda(client, comprado, make_chart):
    """El informe ya se entregó: no se le saca a nadie, se anota la deuda."""
    canjear(comprado.account, "leer_informe", comprado.chart)

    r = _entregar(client)

    assert r.status_code == 200
    comprado.account.refresh_from_db()
    assert comprado.account.deuda == 1
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0


def test_el_reembolso_no_se_descarta_como_duplicado_del_pago(client, comprado):
    """Comparten el pago, no el `external_id`: `stripe:session:` contra
    `stripe:refund:`. Con la misma clave, el reembolso se perdería."""
    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id="stripe:session:cs_1").count() == 1
    assert Movimiento.objects.filter(external_id=f"stripe:refund:{REFUND}").count() == 1


def test_el_mismo_reembolso_dos_veces_revoca_una_sola(client, comprado):
    _entregar(client)
    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(tipo="revocacion").count() == 1
    comprado.account.refresh_from_db()
    assert comprado.account.refund_count == 1


def test_una_compra_de_polar_no_la_atiende_el_webhook_de_stripe(client, make_account):
    """Las filas viejas no tienen `payment_intent`: si el reembolso llegara sin
    uno, un filtro por vacío las engancharía a todas."""
    PasarelaCheckout.objects.create(
        checkout_id="chk_polar", account=make_account(), codigo_producto="informe_natal",
        pasarela="polar",
    )

    r = _entregar(client, _refund(payment_intent=None))

    assert r.status_code == 200
    assert not Movimiento.objects.filter(tipo="revocacion").exists()


def test_una_cuenta_borrada_despues_de_comprar_registra_el_movimiento(client, comprado):
    """Un reembolso puede llegar meses después del borrado de la cuenta: no hay
    a quién bajarle el derecho, pero la contabilidad tiene que cerrar."""
    Account.objects.filter(pk=comprado.account.pk).delete()

    r = _entregar(client)

    assert r.status_code == 200
    assert Movimiento.objects.filter(
        tipo="revocacion", external_id=f"stripe:refund:{REFUND}",
    ).count() == 1


def test_un_reembolso_sin_compra_conocida_pide_reintento(client):
    """El único "no encuentro la compra" que sí se arregla reintentando: el
    reembolso puede llegar antes de que el pago termine de acreditarse."""
    r = _entregar(client)

    assert r.status_code >= 500
    assert not Movimiento.objects.exists()


def test_los_reembolsos_de_la_pasarela_cuentan_para_el_contador(client, comprado):
    """Decidido el 03-09-2026: cuentan todos. El payload no dice quién inició el
    reembolso —`reason` llega vacío— así que distinguirlos sería adivinar, y
    `flagged` no bloquea nada: es una columna del admin para mirar la cuenta."""
    _entregar(client)

    comprado.account.refresh_from_db()
    assert comprado.account.refund_count == 1
