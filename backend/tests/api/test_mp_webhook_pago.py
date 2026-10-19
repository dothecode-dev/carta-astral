"""Webhook de Mercado Pago, pagos: la traducción de RF11. Superficie de PLATA.

Las notificaciones tienen la forma EXACTA medida en el sandbox el 19-10-2026:
query `data.id=<id>&type=payment` (más los parámetros propios de la
`notification_url`, que llegan intactos), headers `x-signature`/`x-request-id`
firmados con `mp_firma.py` (que no importa el código de producción), y el
cuerpo de `payment.created`/`payment.updated`. El pago se lee de la API, que
acá está doblada: el webhook no confía en el cuerpo.
"""

import json
import uuid

import pytest
from django.utils import timezone

from api import cobro
from api.models import Derecho, Movimiento, PasarelaCheckout, Reembolso
from api.pasarelas import mercadopago_api
from api.pasarelas.mercadopago_api import MPError
from tests.api.mp_firma import SECRETO, firmar

URL = "/api/webhooks/mercadopago/"
CHECKOUT = "mp_" + "a" * 32
PRECIO_ARS = 2_500_000
PAGO = 184963579792


@pytest.fixture(autouse=True)
def _secreto(settings):
    settings.MP_WEBHOOK_SECRET = SECRETO


@pytest.fixture(autouse=True)
def _cache_limpia(django_cache_cleared):
    """El aviso de un reembolso no acreditado se deduplica en la caché."""


@pytest.fixture
def avisos(monkeypatch):
    enviados = []
    monkeypatch.setattr(cobro, "avisar_admin", enviados.append)
    return enviados


@pytest.fixture
def mails(monkeypatch):
    enviados = []
    monkeypatch.setattr(
        cobro.notificaciones, "notificar",
        lambda cuenta, evento, contexto, lang: enviados.append((cuenta.pk, evento)),
    )
    return enviados


@pytest.fixture(autouse=True)
def _sin_analitica(monkeypatch):
    monkeypatch.setattr(cobro.analitica, "evento", lambda *a, **k: None)


@pytest.fixture
def pagos(monkeypatch):
    """La API de MP doblada: `pagos[id] = {...}` es lo que devuelve
    `obtener_pago`; `pagos.leidos` y `pagos.reembolsos` registran las llamadas."""

    class _Pagos(dict):
        leidos: list
        reembolsos: list
        fallo_reembolso: Exception | None = None

    tabla = _Pagos()
    tabla.leidos, tabla.reembolsos = [], []

    def obtener(payment_id):
        assert isinstance(payment_id, str)
        tabla.leidos.append(payment_id)
        return tabla[payment_id]

    def reembolsar(payment_id, idempotency_key):
        assert isinstance(payment_id, str)
        tabla.reembolsos.append((payment_id, idempotency_key))
        if tabla.fallo_reembolso is not None:
            raise tabla.fallo_reembolso
        return {"id": 1, "payment_id": int(payment_id)}

    monkeypatch.setattr(mercadopago_api, "obtener_pago", obtener)
    monkeypatch.setattr(mercadopago_api, "reembolsar", reembolsar)
    return tabla


def _pago(pago_id=PAGO, status="approved", status_detail="accredited", currency="ARS",
          monto=25000.0, ref=CHECKOUT, refunds=None, tipo="account_money") -> dict:
    return {
        "id": pago_id, "status": status, "status_detail": status_detail, "currency_id": currency,
        "transaction_amount": monto, "external_reference": ref, "payment_type_id": tipo,
        "refunds": refunds or [],
    }


def _fila(cuenta, **campos) -> PasarelaCheckout:
    datos = dict(
        checkout_id=CHECKOUT, account=cuenta, codigo_producto="informe_natal",
        pasarela=PasarelaCheckout.MERCADOPAGO, moneda="ars", precio_centavos=PRECIO_ARS,
        mp_preferencia_id="pref_1", locale="es",
    )
    datos.update(campos)
    return PasarelaCheckout.objects.create(**datos)


def _notificar(client, pago_id=PAGO, action="payment.created", firma=None, secreto=SECRETO):
    """La notificación tal como la manda MP (modo webhook)."""
    data_id = str(pago_id)
    request_id = str(uuid.uuid4())
    cuerpo = {
        "action": action, "api_version": "v1", "data": {"id": data_id},
        "date_created": "2026-10-19T12:19:02Z", "id": 42256342664138361, "live_mode": True,
        "type": "payment", "user_id": "3777525998",
    }
    return client.post(
        f"{URL}?data.id={data_id}&type=payment&ref={CHECKOUT}",
        data=json.dumps(cuerpo), content_type="application/json",
        HTTP_X_SIGNATURE=firma if firma is not None else firmar(data_id, request_id, secreto=secreto),
        HTTP_X_REQUEST_ID=request_id,
    )


def _otorgados(cuenta) -> int:
    return Movimiento.objects.filter(account=cuenta, tipo="otorgamiento").count()


# --- forma de la notificación ------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("query,cuerpo", [
    ("id=184963579792&topic=payment", {"resource": "184963579792", "topic": "payment"}),
    ("id=45410917328&topic=merchant_order",
     {"resource": "https://api.mercadolibre.com/merchant_orders/45410917328", "topic": "merchant_order"}),
])
def test_ipn_se_ignora_con_200(client, pagos, query, cuerpo):
    r = client.post(
        f"{URL}?{query}", data=json.dumps(cuerpo), content_type="application/json",
        HTTP_USER_AGENT="MercadoPago Feed v2.0 payment",
    )

    assert r.status_code == 200
    assert pagos.leidos == []


@pytest.mark.django_db
@pytest.mark.parametrize("firma", ["ts=1,v1=" + "0" * 64, "", "basura"])
def test_firma_invalida_401_sin_tocar_la_base(client, pagos, make_account, firma, django_assert_num_queries):
    fila = _fila(make_account())
    pagos[str(PAGO)] = _pago()

    with django_assert_num_queries(0):
        r = _notificar(client, firma=firma)

    assert r.status_code == 401
    assert pagos.leidos == []
    fila.refresh_from_db()
    assert fila.acreditado_at is None


@pytest.mark.django_db
def test_firmada_con_otro_secreto_401(client, pagos, make_account):
    _fila(make_account())
    pagos[str(PAGO)] = _pago()

    r = _notificar(client, secreto="otro-secreto")

    assert r.status_code == 401
    assert pagos.leidos == []


@pytest.mark.django_db
def test_sin_secreto_configurado_401(client, pagos, make_account, settings):
    """Fail closed: sin secreto ninguna firma vale, ni siquiera una con secreto vacío."""
    settings.MP_WEBHOOK_SECRET = ""
    _fila(make_account())
    pagos[str(PAGO)] = _pago()

    r = _notificar(client, secreto="")

    assert r.status_code == 401
    assert pagos.leidos == []


@pytest.mark.django_db
def test_sin_data_id_400(client, pagos):
    request_id = str(uuid.uuid4())
    r = client.post(
        f"{URL}?type=payment", data="{}", content_type="application/json",
        HTTP_X_SIGNATURE=firmar("", request_id), HTTP_X_REQUEST_ID=request_id,
    )

    assert r.status_code == 400
    assert pagos.leidos == []


# --- a qué fila va -----------------------------------------------------------------------


@pytest.mark.django_db
def test_pago_ajeno_sin_prefijo_200(client, pagos, avisos):
    """Review Focus 1: la cuenta de MP cobra otras cosas; esos pagos no son
    nuestros ni un error."""
    pagos[str(PAGO)] = _pago(ref="pedido-de-otra-tienda")

    r = _notificar(client)

    assert r.status_code == 200
    assert pagos.leidos == [str(PAGO)]
    assert avisos == []


@pytest.mark.django_db
def test_pago_sin_external_reference_200(client, pagos, avisos):
    pagos[str(PAGO)] = _pago(ref=None)

    assert _notificar(client).status_code == 200
    assert avisos == []


@pytest.mark.django_db
def test_prefijo_sin_fila_500_y_avisa(client, pagos, avisos):
    """Plata cobrada sin nada que entregar, y MP no reintenta tarde (medido en
    sandbox): el 500 no alcanza, tiene que haber aviso."""
    ref = "mp_" + "f" * 32
    pagos[str(PAGO)] = _pago(ref=ref)

    assert _notificar(client).status_code == 500
    assert len(avisos) == 1 and str(PAGO) in avisos[0] and ref in avisos[0]


@pytest.mark.django_db
@pytest.mark.parametrize("ref", ["mp_otra_integracion", "mp_" + "A" * 32, "mp_" + "a" * 31, "mp_" + "a" * 33])
def test_prefijo_mp_con_otro_formato_es_ajeno_200(client, pagos, avisos, ref):
    """Sólo `mp_` + 32 hex (lo que genera `abrir`) es nuestro."""
    pagos[str(PAGO)] = _pago(ref=ref)

    assert _notificar(client).status_code == 200
    assert avisos == []


@pytest.mark.django_db
def test_fila_de_stripe_avisa_y_200(client, pagos, avisos, make_account):
    cuenta = make_account()
    # En pesos a propósito: que lo frene la pasarela y no la moneda.
    _fila(cuenta, pasarela=PasarelaCheckout.STRIPE)
    pagos[str(PAGO)] = _pago()

    assert _notificar(client).status_code == 200
    assert _otorgados(cuenta) == 0
    assert len(avisos) == 1 and str(PAGO) in avisos[0] and "stripe" in avisos[0]


# --- approved ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_aprobado_acredita(client, pagos, avisos, mails, make_account):
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[str(PAGO)] = _pago()

    r = _notificar(client)

    assert r.status_code == 200
    fila.refresh_from_db()
    assert fila.payment_intent == str(PAGO)
    assert fila.acreditado_at is not None
    assert Movimiento.objects.filter(external_id=f"mp:payment:{PAGO}", tipo="otorgamiento").count() == 1
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert mails == [(cuenta.pk, "compra_acreditada")]
    assert avisos == []


@pytest.mark.django_db
def test_monto_con_decimales_se_redondea_a_centavos(client, pagos, avisos, make_account):
    """`transaction_amount` es un float en pesos: 10000.05 * 100 da
    1000004.9999999999, y `int(x * 100)` truncaría un centavo."""
    cuenta = make_account()
    _fila(cuenta, precio_centavos=1_000_005)
    pagos[str(PAGO)] = _pago(monto=10000.05)

    assert _notificar(client).status_code == 200
    assert _otorgados(cuenta) == 1
    assert avisos == []


@pytest.mark.django_db
def test_created_mas_updated_mas_reintento_acreditan_una_vez(client, pagos, avisos, mails, make_account):
    """Review Focus 2: MP manda el mismo pago varias veces (created, reintento
    inmediato, updated). Una sola acreditación, un solo mail."""
    cuenta = make_account()
    _fila(cuenta)
    pagos[str(PAGO)] = _pago()

    for action in ("payment.created", "payment.created", "payment.updated"):
        assert _notificar(client, action=action).status_code == 200

    assert _otorgados(cuenta) == 1
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert mails == [(cuenta.pk, "compra_acreditada")]
    assert avisos == []


@pytest.mark.django_db
def test_aprobado_en_usd_no_acredita_y_avisa(client, pagos, avisos, mails, make_account):
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[str(PAGO)] = _pago(currency="USD", monto=25.0)

    assert _notificar(client).status_code == 200
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert _otorgados(cuenta) == 0
    assert mails == []
    assert len(avisos) == 1 and "usd" in avisos[0]


@pytest.mark.django_db
def test_monto_distinto_no_acredita_y_avisa(client, pagos, avisos, mails, make_account):
    """Review Focus 4."""
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[str(PAGO)] = _pago(monto=1.0)

    assert _notificar(client).status_code == 200
    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert _otorgados(cuenta) == 0
    assert mails == []
    assert len(avisos) == 1 and "monto" in avisos[0]


@pytest.mark.django_db
def test_segundo_pago_aprobado_se_reembolsa_y_no_acredita(client, pagos, avisos, mails, make_account):
    """RF11b: una preferencia admite más de un pago. El segundo se devuelve
    con una clave de idempotencia propia del pago, y no otorga nada."""
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[str(PAGO)] = _pago()
    assert _notificar(client).status_code == 200

    otro = 184963579999
    pagos[str(otro)] = _pago(pago_id=otro)
    r = _notificar(client, pago_id=otro)

    assert r.status_code == 200
    assert pagos.reembolsos == [(str(otro), f"mp:duplicado:{otro}")]
    fila.refresh_from_db()
    assert fila.payment_intent == str(PAGO)
    assert _otorgados(cuenta) == 1
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert mails == [(cuenta.pk, "compra_acreditada")]
    assert len(avisos) == 1 and str(otro) in avisos[0]


@pytest.mark.django_db
def test_segundo_pago_y_su_reembolso_no_revocan_la_compra(client, pagos, avisos, make_account):
    """El duplicado que reembolsamos vuelve como `refunded` con la misma
    external_reference: no revoca lo comprado con el pago legítimo."""
    cuenta = make_account()
    _fila(cuenta)
    pagos[str(PAGO)] = _pago()
    assert _notificar(client).status_code == 200
    otro = 184963579999
    pagos[str(otro)] = _pago(pago_id=otro)
    assert _notificar(client, pago_id=otro).status_code == 200

    pagos[str(otro)] = _pago(
        pago_id=otro, status="refunded", status_detail="refunded",
        refunds=[{"id": 777, "amount": 25000.0, "status": "approved"}],
    )
    assert _notificar(client, pago_id=otro, action="payment.updated").status_code == 200

    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert len(pagos.reembolsos) == 1
    # Uno por el duplicado y otro por su reembolso ignorado (de `cobro`).
    # Cada notificación repetida de ese reembolso vuelve a avisar: sin dedupe.
    assert len(avisos) == 2
    assert "DUPLICADO" in avisos[0] and "no acreditó la compra" in avisos[1]


@pytest.mark.django_db
@pytest.mark.parametrize("fallo", [MPError("Mercado Pago respondió 401", status=401), MPError("id inválido")])
def test_reembolso_del_duplicado_que_falla_avisa_para_hacerlo_a_mano_y_200(
    client, pagos, avisos, make_account, fallo,
):
    """Si MP no deja reembolsar, no se pide reintento (repetiría todo): el
    aviso es la red, y tiene que decir qué pago devolver a mano."""
    cuenta = make_account()
    _fila(cuenta)
    pagos[str(PAGO)] = _pago()
    assert _notificar(client).status_code == 200

    otro = 184963579999
    pagos[str(otro)] = _pago(pago_id=otro)
    pagos.fallo_reembolso = fallo
    r = _notificar(client, pago_id=otro)

    assert r.status_code == 200
    assert _otorgados(cuenta) == 1
    assert len(avisos) == 1 and str(otro) in avisos[0] and "a mano" in avisos[0]


@pytest.mark.django_db
@pytest.mark.parametrize("falla", [False, True])
def test_el_aviso_del_duplicado_nombra_el_pago_que_acredito_leido_bajo_el_lock(
    pagos, avisos, make_account, falla,
):
    """La fila que llega a `_acreditar` se leyó antes del lock: en una carrera
    todavía no sabe qué pago la acreditó. El aviso usa lo leído bajo el lock."""
    from api.pasarelas import mercadopago

    cuenta = make_account()
    vieja = _fila(cuenta)
    PasarelaCheckout.objects.filter(pk=vieja.pk).update(payment_intent=str(PAGO), acreditado_at=timezone.now())
    otro = 184963579999
    if falla:
        pagos.fallo_reembolso = MPError("no", status=400)

    mercadopago._acreditar(vieja, _pago(pago_id=otro), str(otro), "ars")

    assert len(avisos) == 1 and str(otro) in avisos[0] and str(PAGO) in avisos[0]


@pytest.mark.django_db
def test_aprobado_sobre_compra_disputada_avisa_y_200(client, pagos, avisos, mails, make_account):
    cuenta = make_account()
    _fila(cuenta, disputa_id="cb_1")
    pagos[str(PAGO)] = _pago()

    assert _notificar(client).status_code == 200
    assert _otorgados(cuenta) == 0
    assert mails == []
    assert len(avisos) == 1 and "cb_1" in avisos[0] and str(PAGO) in avisos[0]


@pytest.mark.django_db
def test_compra_sin_cuenta_y_sin_mail_500(client, pagos, avisos):
    _fila(None, anonimo=True, mail_comprador="")
    pagos[str(PAGO)] = _pago()

    assert _notificar(client).status_code == 500
    # El aviso lo manda `cobro`, una vez.
    assert len(avisos) == 1


# --- reembolsos, mediación y el resto ------------------------------------------------------


@pytest.fixture
def acreditada(client, pagos, make_account, mails):
    cuenta = make_account()
    _fila(cuenta)
    pagos[str(PAGO)] = _pago()
    assert _notificar(client).status_code == 200
    return cuenta


@pytest.mark.django_db
def test_refunded_revoca_por_cada_refund(client, pagos, avisos, acreditada):
    """Dos reembolsos parciales que suman el total: cada uno con su constancia;
    el segundo aviso del mismo pago no revoca dos veces."""
    pagos[str(PAGO)] = _pago(
        status="refunded", status_detail="refunded",
        refunds=[
            {"id": 501, "amount": 12500.0, "status": "approved"},
            {"id": 502, "amount": 12500.0, "status": "approved"},
        ],
    )

    for _ in range(2):
        assert _notificar(client, action="payment.updated").status_code == 200

    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 0
    assert set(Reembolso.objects.values_list("refund_id", flat=True)) == {"mp:refund:501", "mp:refund:502"}
    assert avisos == []


@pytest.mark.django_db
def test_reembolso_parcial_con_el_pago_aun_aprobado_se_aplica(client, pagos, avisos, acreditada):
    """En MP un reembolso parcial deja el pago `approved` con
    `status_detail=partially_refunded` y el reembolso en `refunds[]`."""
    pagos[str(PAGO)] = _pago(
        status_detail="partially_refunded",
        refunds=[{"id": 601, "amount": 25000.0, "status": "approved"}],
    )

    assert _notificar(client, action="payment.updated").status_code == 200

    assert list(Reembolso.objects.values_list("refund_id", flat=True)) == ["mp:refund:601"]
    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 0


@pytest.mark.django_db
def test_reembolso_rechazado_no_revoca(client, pagos, avisos, acreditada):
    pagos[str(PAGO)] = _pago(
        status_detail="accredited",
        refunds=[{"id": 701, "amount": 25000.0, "status": "rejected"}],
    )

    assert _notificar(client, action="payment.updated").status_code == 200

    assert not Reembolso.objects.exists()
    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 1
    assert avisos == []


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["cancelled", "in_process", "pending"])
def test_reembolso_en_estado_conocido_sin_efecto_no_revoca_ni_avisa(client, pagos, avisos, acreditada, status):
    pagos[str(PAGO)] = _pago(refunds=[{"id": 702, "amount": 25000.0, "status": status}])

    assert _notificar(client, action="payment.updated").status_code == 200

    assert not Reembolso.objects.exists()
    assert avisos == []


@pytest.mark.django_db
@pytest.mark.parametrize("refund", [
    {"id": 703, "amount": 25000.0, "status": "authorized"},
    {"id": 704, "amount": 25000.0},
])
def test_reembolso_en_estado_desconocido_no_revoca_y_avisa(client, pagos, avisos, acreditada, refund):
    """Lista blanca: sólo `approved` revoca. Lo que no conocemos se mira."""
    pagos[str(PAGO)] = _pago(refunds=[refund])

    assert _notificar(client, action="payment.updated").status_code == 200

    assert not Reembolso.objects.exists()
    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 1
    assert len(avisos) == 1 and str(refund["id"]) in avisos[0] and str(PAGO) in avisos[0]


@pytest.mark.django_db
def test_reembolso_sin_id_no_revoca_y_avisa(client, pagos, avisos, acreditada):
    pagos[str(PAGO)] = _pago(
        status="refunded", status_detail="refunded", refunds=[{"amount": 25000.0, "status": "approved"}],
    )

    assert _notificar(client, action="payment.updated").status_code == 200

    assert not Reembolso.objects.exists()
    assert len(avisos) == 1 and str(PAGO) in avisos[0]


@pytest.mark.django_db
def test_in_mediation_solo_avisa(client, pagos, avisos, acreditada):
    pagos[str(PAGO)] = _pago(status="in_mediation", status_detail="pending")

    assert _notificar(client, action="payment.updated").status_code == 200

    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 1
    assert Movimiento.objects.filter(account=acreditada).count() == 1
    assert len(avisos) == 1 and str(PAGO) in avisos[0]


@pytest.mark.django_db
def test_charged_back_avisa_sin_revocar_y_200(client, pagos, avisos, acreditada):
    """La revocación la hace el tópico de contracargos (RF12); el pago en
    `charged_back` sólo avisa, por si ese tópico no está suscripto."""
    fila = PasarelaCheckout.objects.get(account=acreditada)
    pagos[str(PAGO)] = _pago(status="charged_back", status_detail="reimbursed")

    assert _notificar(client, action="payment.updated").status_code == 200

    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 1
    assert len(avisos) == 1
    assert str(PAGO) in avisos[0] and fila.checkout_id in avisos[0] and "contracargo" in avisos[0].lower()
    assert "suscripto" in avisos[0]


@pytest.mark.django_db
@pytest.mark.parametrize("status", ["rejected", "cancelled", "pending", "in_process", "authorized"])
def test_rejected_no_hace_nada(client, pagos, avisos, mails, make_account, status):
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[str(PAGO)] = _pago(status=status, status_detail="cc_rejected_other_reason")

    assert _notificar(client).status_code == 200

    fila.refresh_from_db()
    assert fila.acreditado_at is None
    assert fila.vencido_at is None
    assert _otorgados(cuenta) == 0
    assert mails == [] and avisos == []


@pytest.mark.django_db
@pytest.mark.parametrize("fallo", [MPError("Mercado Pago no contestó (ConnectTimeout)"), MPError("x", status=503)])
def test_mp_caido_al_leer_el_pago_500(client, monkeypatch, make_account, fallo):
    cuenta = make_account()
    _fila(cuenta)

    def caido(payment_id):
        raise fallo

    monkeypatch.setattr(mercadopago_api, "obtener_pago", caido)

    assert _notificar(client).status_code == 500
    assert _otorgados(cuenta) == 0


@pytest.mark.django_db
def test_reembolso_se_aplica_aunque_acreditar_falle(client, pagos, avisos, acreditada, monkeypatch):
    """Code review B: un fallo al (re)acreditar el pago no puede saltear sus
    reembolsos. MP no reintenta tarde: ese reembolso se perdería."""
    pagos[str(PAGO)] = _pago(
        status_detail="partially_refunded",
        refunds=[{"id": 801, "amount": 25000.0, "status": "approved"}],
    )

    def explota(*_a, **_k):
        raise RuntimeError("se cayó el arranque")

    monkeypatch.setattr(cobro, "acreditar", explota)

    assert _notificar(client, action="payment.updated").status_code == 500
    assert list(Reembolso.objects.values_list("refund_id", flat=True)) == ["mp:refund:801"]
    assert Derecho.objects.get(account=acreditada, codigo_producto="informe_natal").cantidad_restante == 0


@pytest.mark.django_db
def test_payment_updated_tras_rendirse_el_informe_no_lo_rearranca(
    client, pagos, avisos, mails, make_account, make_chart, monkeypatch,
):
    """Code review A, por el webhook: el informe se rindió (borrado, derecho
    devuelto) y después llega un `payment.updated` del mismo pago, p. ej. por
    un reembolso parcial rechazado. Ni informe nuevo, ni derecho, ni mail."""
    from api import interpretation_service
    from api.canje import devolver
    from api.models import Interpretation
    from api.sujetos import sujeto_natal

    monkeypatch.setattr(interpretation_service, "arrancar_en_hilo", lambda *_a: None)
    cuenta = make_account()
    fila = _fila(cuenta, sujeto=sujeto_natal(make_chart(account=cuenta)))
    pagos[str(PAGO)] = _pago()
    assert _notificar(client).status_code == 200
    interpretacion = Interpretation.objects.get(sujeto=fila.sujeto)
    devolver(cuenta, "informe_natal", external_id=f"informe:{interpretacion.pk}:devolucion", sujeto=fila.sujeto)
    interpretacion.delete()
    mails.clear()

    pagos[str(PAGO)] = _pago(refunds=[{"id": 901, "amount": 100.0, "status": "rejected"}])
    assert _notificar(client, action="payment.updated").status_code == 200

    assert not Interpretation.objects.filter(sujeto=fila.sujeto).exists()
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    assert mails == [] and avisos == []
