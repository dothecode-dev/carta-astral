"""Pagar con Stripe deja el informe escribiéndose: tests 17-20 de la spec.

Es el incidente del 02-09-2026: el pago se acreditó, el derecho se canjeó
contra la carta, y nadie creó la `Interpretation`. Quien pagó volvió y encontró
el botón de comprar otra vez, con el derecho ya gastado.

Stripe le da 10 segundos al webhook antes de redirigir al comprador, así que lo
que corre en el hilo de la entrega es sólo la creación de la fila —rápida, y es
la que `reanudar_informes` encuentra si el hilo muere—; la generación se lanza
sin bloquear.
"""

import json

import pytest

from api import compra_service, interpretation_service as svc, webhooks_stripe
from api.models import Interpretation, Movimiento, PasarelaCheckout
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
SESSION = "cs_test_informe"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {"price_natal": "informe_natal", "price_pack": "pack_5_natal"}


@pytest.fixture
def sin_hilo(monkeypatch):
    """Registra los arranques en vez de lanzarlos: el hilo real llama al modelo."""
    arrancados = []
    monkeypatch.setattr(
        svc, "arrancar_en_hilo",
        lambda interpretacion, chart, account: arrancados.append(interpretacion),
    )
    return arrancados


def _entregar(client, monkeypatch, precio="price_natal", monto=2900):
    sesion = {
        "id": SESSION, "payment_status": "paid",
        "amount_subtotal": monto, "amount_total": monto,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_1", "metadata": {},
        "line_items": {"data": [{"price": {"id": precio}, "quantity": 1}]},
    }
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
    cuerpo = json.dumps({
        "id": "evt_1", "type": "checkout.session.completed",
        "data": {"object": {"id": SESSION}},
    }).encode()
    return client.post(
        URL, data=cuerpo, content_type="application/json",
        HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
    )


def _compra(cuenta, chart, codigo="informe_natal"):
    return PasarelaCheckout.objects.create(
        checkout_id=SESSION, account=cuenta, codigo_producto=codigo, chart=chart,
    )


def test_una_compra_suelta_con_carta_deja_el_informe_iniciado(
    client, monkeypatch, make_account, make_chart, sin_hilo,
):
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    _compra(cuenta, carta)

    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert Interpretation.objects.filter(chart=carta).count() == 1
    assert len(sin_hilo) == 1


def test_un_pack_no_arranca_ningun_informe(
    client, monkeypatch, make_account, make_chart, sin_hilo,
):
    """Cinco informes se usan cuando la persona quiera: elegirle una carta
    sería gastarle uno sin que lo pida."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    _compra(cuenta, carta, codigo="pack_5_natal")
    from api.catalogo import producto

    r = _entregar(client, monkeypatch, precio="price_pack",
                  monto=producto("pack_5_natal").precio_centavos)

    assert r.status_code == 200
    assert not Interpretation.objects.exists()
    assert not sin_hilo


def test_en_mantenimiento_acredita_y_deja_la_fila_sin_lanzar_el_hilo(
    client, monkeypatch, make_account, make_chart, sin_hilo,
):
    """Hay un deploy en curso: el hilo moriría con el contenedor viejo a mitad
    de camino. La fila queda creada y `reanudar_informes` la termina."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    _compra(cuenta, carta)
    monkeypatch.setattr(compra_service.mantenimiento, "activo", lambda: True)

    r = _entregar(client, monkeypatch)

    assert r.status_code == 200
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1
    assert Interpretation.objects.filter(chart=carta).count() == 1
    assert not sin_hilo


def test_si_el_informe_no_arranca_la_plata_queda_acreditada_y_se_reintenta(
    client, monkeypatch, make_account, make_chart,
):
    """La plata ya está: el 5xx no la desacredita (los requests no corren en
    transacción) y sí hace que Stripe vuelva a intentar el arranque, que es
    idempotente porque `iniciar_generacion` usa `get_or_create`."""
    cuenta = make_account()
    carta = make_chart(account=cuenta)
    _compra(cuenta, carta)

    def explota(*_a, **_k):
        raise RuntimeError("el modelo no responde")

    monkeypatch.setattr(svc, "iniciar_generacion", explota)

    r = _entregar(client, monkeypatch)

    assert r.status_code >= 500
    assert Movimiento.objects.filter(external_id=f"stripe:session:{SESSION}").count() == 1
