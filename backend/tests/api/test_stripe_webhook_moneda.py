"""El webhook con dos monedas: acredita sólo el par (moneda, monto) que la
fila congeló; lo demás se rechaza con aviso al admin. Spec cobro-brl-pix,
RF10–RF12, EC1, EC15, Review Focus 2 y 3."""

import json

import pytest
from django.utils import timezone

from api import avisos, cobro, webhooks_stripe
from api.models import Derecho, PasarelaCheckout
from api.sujetos import sujeto_natal
from tests.api.stripe_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/stripe/"
SESSION = "cs_test_brl"


@pytest.fixture(autouse=True)
def _configurado(settings):
    settings.STRIPE_WEBHOOK_SECRET = SECRETO
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}


@pytest.fixture
def avisos_enviados(monkeypatch):
    enviados = []
    monkeypatch.setattr(avisos, "avisar_admin", lambda texto: enviados.append(texto))
    monkeypatch.setattr(cobro, "avisar", lambda texto: enviados.append(texto))
    return enviados


def _sesion(moneda="brl", monto=14900, **cambios) -> dict:
    sesion = {
        "id": SESSION, "payment_status": "paid", "currency": moneda,
        "amount_subtotal": monto, "amount_total": monto,
        "total_details": {"amount_tax": 0, "amount_discount": 0},
        "payment_intent": "pi_brl", "metadata": {},
        "line_items": {"data": [{"price": {"product": "prod_natal"}, "quantity": 1}]},
    }
    sesion.update(cambios)
    return sesion


def _entregar(client, monkeypatch, sesion, tipo="checkout.session.completed"):
    monkeypatch.setattr(webhooks_stripe, "obtener_sesion", lambda _sid: sesion)
    cuerpo = json.dumps({
        "id": "evt_brl", "type": tipo,
        "data": {"object": {"id": SESSION, "object": "checkout.session"}},
    }).encode()
    return client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))


@pytest.fixture
def compra_brl(make_account, make_chart):
    cuenta = make_account()
    return PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal",
        sujeto=sujeto_natal(make_chart(account=cuenta)), moneda="brl", precio_centavos=14900,
    )


def _restante(cuenta):
    d = Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").first()
    return d.cantidad_restante if d else 0


def test_una_compra_en_reales_se_acredita_con_su_monto_en_reales(client, monkeypatch, compra_brl, sin_hilo, avisos_enviados):
    r = _entregar(client, monkeypatch, _sesion())

    assert r.status_code == 200
    compra_brl.refresh_from_db()
    assert compra_brl.acreditado_at is not None
    assert avisos_enviados == []


def test_la_moneda_de_la_sesion_tiene_que_ser_la_de_la_fila(client, monkeypatch, compra_brl, avisos_enviados):
    """14900 centavos de dólar NO son 14900 centavos de real (Review Focus 2)."""
    r = _entregar(client, monkeypatch, _sesion(moneda="usd", monto=14900))

    assert r.status_code == 200  # definitivo: reintentar no lo arregla
    compra_brl.refresh_from_db()
    assert compra_brl.acreditado_at is None
    assert _restante(compra_brl.account) == 0
    assert any("usd" in a and "brl" in a and SESSION in a for a in avisos_enviados)


def test_el_monto_en_reales_tiene_que_ser_el_congelado(client, monkeypatch, compra_brl, avisos_enviados):
    _entregar(client, monkeypatch, _sesion(monto=2490))  # el precio REAL, no el de la fila

    compra_brl.refresh_from_db()
    assert compra_brl.acreditado_at is None
    assert any("2490" in a for a in avisos_enviados)


def test_una_fila_abierta_en_usd_antes_del_deploy_se_acredita_igual(client, monkeypatch, make_account, make_chart, sin_hilo):
    """EC1: la migración deja `moneda="usd"` y el precio congelado; la sesión
    vieja llega en `usd` con ese monto."""
    cuenta = make_account()
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal",
        sujeto=sujeto_natal(make_chart(account=cuenta)), precio_centavos=2900,
    )

    _entregar(client, monkeypatch, _sesion(moneda="usd", monto=2900))

    assert _restante(cuenta) == 0  # ya se canjeó en el informe
    assert PasarelaCheckout.objects.get(checkout_id=SESSION).acreditado_at is not None


def test_el_codigo_sale_de_la_fila_y_el_product_lo_confirma(client, monkeypatch, compra_brl, avisos_enviados):
    sesion = _sesion()
    sesion["line_items"]["data"][0]["price"]["product"] = "prod_otro"

    _entregar(client, monkeypatch, sesion)

    compra_brl.refresh_from_db()
    assert compra_brl.acreditado_at is None
    assert any("prod_otro" in a for a in avisos_enviados)


def test_sin_fila_no_se_acredita_en_ninguna_moneda(client, monkeypatch, make_account, avisos_enviados):
    """Sin fila no hay moneda congelada contra la que comparar (RF10). Desde
    la fase 2 (R3) tampoco en usd: sin fila no se acredita y se avisa."""
    cuenta = make_account()

    _entregar(client, monkeypatch, _sesion(metadata={"account_id": str(cuenta.pk)}))

    assert _restante(cuenta) == 0
    assert any("SIN fila" in a for a in avisos_enviados)


def test_un_pago_que_llega_sobre_una_fila_vencida_se_acredita_y_avisa(client, monkeypatch, compra_brl, sin_hilo, avisos_enviados):
    """EC15 / Review Focus 3: el QR de Pix se pagó después de que la sesión
    venció. La plata entró: se entrega, y se avisa para mirarlo."""
    compra_brl.vencido_at = timezone.now()
    compra_brl.save(update_fields=["vencido_at"])

    _entregar(client, monkeypatch, _sesion())

    compra_brl.refresh_from_db()
    assert compra_brl.acreditado_at is not None
    assert any("vencida" in a for a in avisos_enviados)


def test_un_pix_abandonado_vence_como_una_tarjeta(client, monkeypatch, compra_brl):
    """MEDIDO el 13-10-2026: el Pix no pagado deja la sesión `open` hasta
    `expires_at`, y entonces llega `expired`, igual que con tarjeta (RF14)."""
    cuerpo = json.dumps({
        "id": "evt_exp", "type": "checkout.session.expired",
        "data": {"object": {"id": SESSION, "object": "checkout.session"}},
    }).encode()
    r = client.post(URL, data=cuerpo, content_type="application/json", HTTP_STRIPE_SIGNATURE=firmar(cuerpo))

    assert r.status_code == 200
    compra_brl.refresh_from_db()
    assert compra_brl.vencido_at is not None and compra_brl.acreditado_at is None


def test_el_uso_del_cupon_y_la_analitica_llevan_la_moneda(client, monkeypatch, make_account, make_chart, sin_hilo):
    from api import analitica
    from api.models import Cupon, CuponUso

    cuenta = make_account()
    cupon = Cupon.objects.create(codigo="TREINTA", porcentaje=30, productos=["informe_natal"], usos_maximos=5, stripe_promotion_code_id="promo_1")
    PasarelaCheckout.objects.create(
        pasarela=PasarelaCheckout.STRIPE, checkout_id=SESSION, account=cuenta, codigo_producto="informe_natal",
        sujeto=sujeto_natal(make_chart(account=cuenta)), moneda="brl", precio_centavos=14900,
        cupon=cupon, descuento_centavos=4470,
    )
    medidos = []
    monkeypatch.setattr(analitica, "evento", lambda acc, nombre, props: medidos.append(props))
    sesion = _sesion(total_details={"amount_tax": 0, "amount_discount": 4470}, discounts=[{"promotion_code": "promo_1"}])
    sesion["amount_total"] = 10430

    _entregar(client, monkeypatch, sesion)

    uso = CuponUso.objects.get()
    assert (uso.moneda, uso.monto_pagado_centavos, uso.descuento_centavos) == ("brl", 10430, 4470)
    assert medidos[0]["moneda"] == "brl" and medidos[0]["monto_centavos"] == 10430


@pytest.mark.parametrize("pi", [
    # El tipo del PaymentMethod usado gana sobre `payment_method_types[0]`.
    {"id": "pi_brl", "payment_method_types": ["card", "pix"], "payment_method": {"id": "pm_1", "type": "pix"}},
    # Respaldo: PI sin el PaymentMethod expandido.
    {"id": "pi_brl", "payment_method_types": ["pix"]},
])
def test_el_medio_de_pago_llega_al_aviso(client, monkeypatch, compra_brl, sin_hilo, pi):
    from api import notificaciones

    avisados = []
    monkeypatch.setattr(notificaciones, "notificar", lambda cuenta, evento, ctx, lang: avisados.append(ctx))

    _entregar(client, monkeypatch, _sesion(payment_intent=pi))

    assert avisados[0]["medio"] == "pix"
    compra_brl.refresh_from_db()
    assert compra_brl.pago_id == "pi_brl"
