import dataclasses

import pytest

from api import catalogo

#: El precio de lista con el que corren los tests de la mecánica del cobro
#: —webhook, cupones, reembolsos, compras—. Prueban cómo se valida y se
#: acredita un precio cualquiera, no cuánto vale hoy el informe: si leyeran el
#: precio real, cada cambio de precio rompería decenas de tests que no tienen
#: nada que ver. Cuánto vale de verdad lo fijan los tests marcados
#: `catalogo_real` (test_catalogo.py).
PRECIO_DE_PRUEBA = 2900


@pytest.fixture(autouse=True)
def _precio_de_prueba(request, monkeypatch):
    if request.node.get_closest_marker("catalogo_real"):
        return
    monkeypatch.setitem(
        catalogo.CATALOGO, "informe_natal",
        dataclasses.replace(catalogo.CATALOGO["informe_natal"], precio_centavos=PRECIO_DE_PRUEBA),
    )


@pytest.fixture
def cupon_100():
    """Un regalo del 100 % del informe natal, de un solo uso."""
    from api.models import Cupon

    return Cupon.objects.create(
        codigo="REGALO", porcentaje=100, productos=["informe_natal"], usos_maximos=1,
    )


# --- «Pagar es entrar»: la compra anónima que el webhook adjudica (Tasks 4-6) ---

#: El `checkout_id` de la compra anónima de los tests. No se llama `SESSION`
#: para no confundirse con el `SESSION` local de cada archivo de webhooks.
SESSION_ANONIMA = "cs_test_anonima"
PI_ANONIMA = "pi_anonima"
PRECIO_ANONIMA = "price_natal"


def sesion_anonima(**cambios) -> dict:
    """La sesión pagada que devuelve la API al re-consultarla, sin mail."""
    sesion = {
        "id": SESSION_ANONIMA,
        "payment_status": "paid",
        "amount_subtotal": 2900,
        "amount_total": 2900,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": PI_ANONIMA,
        "metadata": {},
        "line_items": {"data": [{"price": {"id": PRECIO_ANONIMA}, "quantity": 1}]},
    }
    sesion.update(cambios)
    return sesion


def con_mail(email, **cambios) -> dict:
    """La sesión anónima pagada con `email` en `customer_details`."""
    return sesion_anonima(customer_details={"email": email}, **cambios)


@pytest.fixture
def anonima(make_chart):
    """Un checkout abierto sin cuenta, como lo deja `compra_anonima.abrir`: la
    carta sin dueño y (por `PasarelaCheckout.save`) su sujeto natal también."""
    from api.models import PasarelaCheckout

    return PasarelaCheckout.objects.create(
        checkout_id=SESSION_ANONIMA, account=None, codigo_producto="informe_natal",
        chart=make_chart(account=None), anonimo=True, nonce_hash="x" * 64,
        precio_centavos=2900,
    )


@pytest.fixture
def sin_hilo(monkeypatch):
    """`arrancar_informe` crea la fila del informe pero no lanza el hilo real."""
    from api import interpretation_service

    arrancados = []
    monkeypatch.setattr(
        interpretation_service, "arrancar_en_hilo",
        lambda interpretacion, chart, account: arrancados.append(interpretacion),
    )
    return arrancados


@pytest.fixture
def entregar_anonima(client, monkeypatch, settings):
    """Entrega firmada al webhook de un evento de pago sobre la compra anónima.

    `entregar_anonima(sesion, tipo=...)`: `sesion` es lo que devuelve la
    re-consulta a la API de Stripe."""
    import json

    from api import webhooks_stripe
    from tests.api.stripe_firma import SECRETO, firmar

    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRECIOS = {PRECIO_ANONIMA: "informe_natal"}

    def _entregar(sesion, tipo="checkout.session.completed", evt="evt_anonima"):
        monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
        cuerpo = json.dumps({
            "id": evt, "type": tipo,
            "data": {"object": {"id": SESSION_ANONIMA, "object": "checkout.session"}},
        }).encode()
        return client.post(
            "/api/webhooks/stripe/", data=cuerpo, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=firmar(cuerpo),
        )

    return _entregar
