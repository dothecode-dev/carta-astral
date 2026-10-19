"""Webhook de Mercado Pago, reclamos y contracargos (RF12). Superficie de PLATA.

Reclamo: notificación REAL medida en el sandbox el 19-10-2026. La query trae
`data.id=<uuid de la notificación>&type=topic_claims_integration_wh` y la firma
se arma con ese uuid; el id del reclamo viene en el CUERPO (`data.id`).

Contracargo: el sandbox NO permite simularlo. Se asume el mismo reparto
query/cuerpo que el reclamo y, según la documentación de MP, el cuerpo trae
`data.id` (el contracargo) y `data.payment_id`. El contracargo se lee de la API
(doblada acá) y el pago tiene que figurar en él: el cuerpo no está firmado.
"""

import json
import uuid

import pytest

from api import cobro
from api.models import Derecho, Disputa, MailBloqueado, Movimiento, PasarelaCheckout
from api.pasarelas import mercadopago_api
from tests.api.mp_firma import SECRETO, firmar

pytestmark = pytest.mark.django_db

URL = "/api/webhooks/mercadopago/"
CHECKOUT = "mp_" + "b" * 32
PRECIO_ARS = 2_500_000
PAGO = 184963579792
CONTRACARGO = "236000123456"
RECLAMO = 5596641589
MAIL = "ana@mail.com"
#: El cliente de verdad, para los tests que doblan sólo el transporte (`_pedir`).
_OBTENER_CONTRACARGO_REAL = mercadopago_api.obtener_contracargo


@pytest.fixture(autouse=True)
def _secreto(settings):
    settings.MP_WEBHOOK_SECRET = SECRETO


@pytest.fixture(autouse=True)
def _sin_analitica_ni_mails(monkeypatch):
    monkeypatch.setattr(cobro.analitica, "evento", lambda *a, **k: None)
    monkeypatch.setattr(cobro.notificaciones, "notificar", lambda *a, **k: None)


@pytest.fixture
def avisos(monkeypatch):
    enviados: list[str] = []
    monkeypatch.setattr(cobro, "avisar_admin", enviados.append)
    return enviados


@pytest.fixture
def api_mp(monkeypatch):
    """La API de MP doblada: `api_mp.pagos[id]` y `api_mp.contracargos[id]`."""

    class _Api:
        pagos: dict = {}
        contracargos: dict = {}
        leidos: list = []

    tabla = _Api()
    tabla.pagos, tabla.contracargos, tabla.leidos = {}, {}, []

    def obtener_pago(payment_id):
        return tabla.pagos[payment_id]

    def obtener_contracargo(chargeback_id):
        assert isinstance(chargeback_id, str)
        tabla.leidos.append(chargeback_id)
        return tabla.contracargos[chargeback_id]

    monkeypatch.setattr(mercadopago_api, "obtener_pago", obtener_pago)
    monkeypatch.setattr(mercadopago_api, "obtener_contracargo", obtener_contracargo)
    return tabla


def _contracargo(cid=CONTRACARGO, pagos=(PAGO,), monto=25000.0) -> dict:
    """Forma documentada de `GET /v1/chargebacks/{id}` (no medida: V4)."""
    return {
        "id": cid, "payments": list(pagos), "currency": "ARS", "amount": monto,
        "coverage_applied": False, "coverage_eligible": True, "documentation_required": True,
        "documentation_status": "pending", "stage": "chargeback", "reason": "fraud",
        "date_created": "2026-10-19T09:00:00.000-04:00",
    }


def _post(client, tipo: str, cuerpo: dict, firma=None):
    """Como lo manda MP: el `data.id` de la query es el uuid de la notificación
    y es lo que se firma; el negocio va en el cuerpo."""
    notificacion = str(uuid.uuid4())
    request_id = str(uuid.uuid4())
    cuerpo = {"id": notificacion, "type": tipo, **cuerpo}
    return client.post(
        f"{URL}?data.id={notificacion}&type={tipo}",
        data=json.dumps(cuerpo), content_type="application/json",
        HTTP_X_SIGNATURE=firma if firma is not None else firmar(notificacion, request_id),
        HTTP_X_REQUEST_ID=request_id,
    )


def _reclamo(client, firma=None):
    return _post(client, "topic_claims_integration_wh", {
        "action": "updated", "api_version": "v1",
        "data": {"id": RECLAMO, "resource": f"/v1/claims/{RECLAMO}"},
        "date_created": "2026-10-19T08:47:22-04:00", "live_mode": True, "user_id": 3777525998,
    }, firma=firma)


def _notificar_contracargo(client, cid=CONTRACARGO, payment_id=PAGO, firma=None, data=None):
    return _post(client, "topic_chargebacks_wh", {
        "action": "created", "api_version": "v1",
        "data": data if data is not None else {"id": cid, "payment_id": payment_id},
        "date_created": "2026-10-19T09:00:00-04:00", "live_mode": True, "user_id": 3777525998,
    }, firma=firma)


@pytest.fixture
def acreditada(client, api_mp, avisos, make_account):
    """Una compra en pesos acreditada por el webhook de pagos real."""
    cuenta = make_account(email=MAIL)
    PasarelaCheckout.objects.create(
        checkout_id=CHECKOUT, account=cuenta, codigo_producto="informe_natal",
        pasarela=PasarelaCheckout.MERCADOPAGO, moneda="ars", precio_centavos=PRECIO_ARS,
        mp_preferencia_id="pref_1", locale="es",
    )
    api_mp.pagos[str(PAGO)] = {
        "id": PAGO, "status": "approved", "status_detail": "accredited", "currency_id": "ARS",
        "transaction_amount": 25000.0, "external_reference": CHECKOUT, "payment_type_id": "account_money",
        "refunds": [],
    }
    notificacion = str(PAGO)
    request_id = str(uuid.uuid4())
    r = client.post(
        f"{URL}?data.id={notificacion}&type=payment",
        data=json.dumps({"action": "payment.created", "data": {"id": notificacion}, "type": "payment"}),
        content_type="application/json",
        HTTP_X_SIGNATURE=firmar(notificacion, request_id), HTTP_X_REQUEST_ID=request_id,
    )
    assert r.status_code == 200
    avisos.clear()
    return cuenta


def _restante(cuenta) -> int:
    return Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante


# --- reclamos ------------------------------------------------------------------------------


def test_reclamo_solo_avisa(client, api_mp, avisos, acreditada):
    r = _reclamo(client)

    assert r.status_code == 200
    assert len(avisos) == 1 and str(RECLAMO) in avisos[0]
    assert _restante(acreditada) == 1
    assert not Disputa.objects.exists()
    assert not MailBloqueado.bloqueado(MAIL)
    assert api_mp.leidos == []


@pytest.mark.parametrize("tipo", ["topic_claims_integration_wh", "topic_chargebacks_wh"])
def test_reclamo_y_contracargo_con_firma_invalida_401(client, api_mp, avisos, tipo):
    r = _post(client, tipo, {"data": {"id": "1", "payment_id": PAGO}}, firma="ts=1,v1=" + "0" * 64)

    assert r.status_code == 401
    assert avisos == []
    assert api_mp.leidos == []


@pytest.mark.parametrize("tipo", ["topic_claims_integration_wh", "topic_chargebacks_wh"])
def test_reclamo_y_contracargo_sin_secreto_401(client, api_mp, avisos, settings, tipo):
    settings.MP_WEBHOOK_SECRET = ""

    r = _post(client, tipo, {"data": {"id": "1", "payment_id": PAGO}})

    assert r.status_code == 401
    assert avisos == []


def test_reclamo_sin_id_en_el_cuerpo_avisa_y_200(client, avisos):
    r = _post(client, "topic_claims_integration_wh", {"data": {}})

    assert r.status_code == 200
    assert len(avisos) == 1 and "reclamo" in avisos[0].lower()


# --- contracargos --------------------------------------------------------------------------


def test_contracargo_revoca_bloquea_mail_y_avisa(client, api_mp, avisos, acreditada):
    api_mp.contracargos[CONTRACARGO] = _contracargo()

    r = _notificar_contracargo(client)

    assert r.status_code == 200
    assert api_mp.leidos == [CONTRACARGO]
    fila = PasarelaCheckout.objects.get(checkout_id=CHECKOUT)
    assert fila.disputa_id == f"mp:chargeback:{CONTRACARGO}"
    assert fila.reembolsado_centavos == PRECIO_ARS
    assert _restante(acreditada) == 0
    assert MailBloqueado.bloqueado(MAIL)
    disputa = Disputa.objects.get(dispute_id=f"mp:chargeback:{CONTRACARGO}")
    assert disputa.fila == fila and disputa.monto_anotado == PRECIO_ARS
    assert len(avisos) == 1
    assert CONTRACARGO in avisos[0] and CHECKOUT in avisos[0] and "ars" in avisos[0]
    assert "contracargo MP" in avisos[0]
    assert MAIL not in avisos[0]


def test_contracargo_monto_con_decimales_se_redondea(client, api_mp, avisos, acreditada):
    # 0.29 * 100 = 28.999999999999996: con `int` anotaría 28.
    api_mp.contracargos[CONTRACARGO] = _contracargo(monto=0.29)

    assert _notificar_contracargo(client).status_code == 200

    assert Disputa.objects.get().monto_anotado == 29


def test_contracargo_repetido_no_aplica_dos_veces(client, api_mp, avisos, acreditada):
    api_mp.contracargos[CONTRACARGO] = _contracargo()

    assert _notificar_contracargo(client).status_code == 200
    assert _notificar_contracargo(client).status_code == 200

    assert Disputa.objects.count() == 1
    assert Movimiento.objects.filter(account=acreditada, tipo="revocacion").count() == 1
    assert PasarelaCheckout.objects.get(checkout_id=CHECKOUT).reembolsado_centavos == PRECIO_ARS
    assert _restante(acreditada) == 0


def test_segunda_notificacion_del_contracargo_solo_avisa(client, api_mp, avisos, acreditada):
    """D3: la resolución no se automatiza. Una notificación posterior del mismo
    contracargo (p. ej. resuelto a favor) no repone nada: avisa para revisarlo."""
    api_mp.contracargos[CONTRACARGO] = _contracargo()
    assert _notificar_contracargo(client).status_code == 200
    avisos.clear()
    api_mp.contracargos[CONTRACARGO] = {**_contracargo(), "coverage_applied": True, "stage": "closed"}

    r = _notificar_contracargo(client)

    assert r.status_code == 200
    assert len(avisos) == 1
    assert CONTRACARGO in avisos[0] and "revisar a mano" in avisos[0]
    assert _restante(acreditada) == 0
    assert MailBloqueado.bloqueado(MAIL)
    assert Disputa.objects.get().estado == Disputa.ABIERTA


def test_contracargo_sin_compra_500(client, api_mp, avisos):
    api_mp.contracargos[CONTRACARGO] = _contracargo()

    r = _notificar_contracargo(client)

    assert r.status_code == 500
    assert not Disputa.objects.exists()
    # MP no reintenta tarde tras un 500 (medido en sandbox): el aviso es la red.
    assert len(avisos) == 1 and CONTRACARGO in avisos[0] and str(PAGO) in avisos[0]


def test_contracargo_sobre_fila_de_stripe_con_el_mismo_id_500(client, api_mp, avisos, make_account):
    """La fila se busca sólo entre las de MP: un `payment_intent` de Stripe
    nunca coincide, pero la búsqueda no lo deja librado a la suerte."""
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=make_account(email=MAIL), codigo_producto="informe_natal",
        moneda="ars", precio_centavos=PRECIO_ARS, payment_intent=str(PAGO),
    )
    api_mp.contracargos[CONTRACARGO] = _contracargo()

    assert _notificar_contracargo(client).status_code == 500
    assert not Disputa.objects.exists()


@pytest.mark.parametrize("data", [{}, {"id": CONTRACARGO}, {"payment_id": PAGO}, {"id": "", "payment_id": ""}])
def test_contracargo_sin_ids_en_el_cuerpo_avisa_y_200(client, api_mp, avisos, data):
    r = _notificar_contracargo(client, data=data)

    assert r.status_code == 200
    assert api_mp.leidos == []
    assert len(avisos) == 1 and "contracargo" in avisos[0].lower()


def test_contracargo_cuyo_pago_no_coincide_con_la_api_no_toca_nada_y_avisa(client, api_mp, avisos, acreditada):
    """El cuerpo no está firmado: el pago tiene que figurar en el contracargo
    que devuelve la API, o se avisa sin tocar la compra."""
    api_mp.contracargos[CONTRACARGO] = _contracargo(pagos=(999,))

    r = _notificar_contracargo(client)

    assert r.status_code == 200
    assert not Disputa.objects.exists()
    assert _restante(acreditada) == 1
    assert len(avisos) == 1 and CONTRACARGO in avisos[0] and "revisar" in avisos[0]


def test_contracargo_con_mp_caido_500(client, api_mp, avisos, acreditada, monkeypatch):
    def caido(chargeback_id):
        raise mercadopago_api.MPError("timeout")

    monkeypatch.setattr(mercadopago_api, "obtener_contracargo", caido)

    assert _notificar_contracargo(client).status_code == 500
    assert not Disputa.objects.exists()


def test_otro_tipo_sigue_siendo_200_sin_procesar(client, api_mp, avisos):
    r = client.post(f"{URL}?data.id=1&type=point_integration_wh", data="{}", content_type="application/json")

    assert r.status_code == 200
    assert avisos == [] and api_mp.leidos == []


def test_contracargo_firmado_con_cuerpo_que_no_es_json_avisa_y_200(client, api_mp, avisos):
    notificacion, request_id = str(uuid.uuid4()), str(uuid.uuid4())

    r = client.post(
        f"{URL}?data.id={notificacion}&type=topic_chargebacks_wh", data="no{json",
        content_type="application/json",
        HTTP_X_SIGNATURE=firmar(notificacion, request_id), HTTP_X_REQUEST_ID=request_id,
    )

    assert r.status_code == 200
    assert api_mp.leidos == []
    assert len(avisos) == 1 and "contracargo" in avisos[0].lower()


# --- respuestas de la API con forma inesperada: fallar del lado seguro, con aviso ---------
#
# MP no reintenta tarde tras un 500 (medido en sandbox): un 500 mudo es plata
# sin rastro. Lo que un reintento no arregla responde 200 y avisa.


@pytest.fixture
def transporte(monkeypatch, settings):
    """Deshace el doble de `obtener_contracargo`: el test dobla `_pedir`."""
    settings.MP_ACCESS_TOKEN = "TEST-token"
    monkeypatch.setattr(mercadopago_api, "obtener_contracargo", _OBTENER_CONTRACARGO_REAL)


def _sin_efecto(cuenta, avisos, r) -> None:
    assert r.status_code == 200
    assert not Disputa.objects.exists()
    assert _restante(cuenta) == 1
    assert not MailBloqueado.bloqueado(MAIL)
    assert len(avisos) == 1 and CONTRACARGO in avisos[0] and "revisar a mano" in avisos[0]


@pytest.mark.parametrize("cambio", [
    {"payments": [{"id": PAGO}]},
    {"payments": PAGO},
    {"payments": str(PAGO)},
    {"payments": [True]},
])
def test_contracargo_con_payments_de_otra_forma_avisa_y_no_revoca(client, api_mp, avisos, acreditada, cambio):
    api_mp.contracargos[CONTRACARGO] = {**_contracargo(), **cambio}

    _sin_efecto(acreditada, avisos, _notificar_contracargo(client))


def test_contracargo_sin_payments_avisa_y_no_revoca(client, api_mp, avisos, acreditada):
    contracargo = _contracargo()
    del contracargo["payments"]
    api_mp.contracargos[CONTRACARGO] = contracargo

    _sin_efecto(acreditada, avisos, _notificar_contracargo(client))


@pytest.mark.parametrize("monto", ["sin", None, 0, 0.0, -100.0, "abc", True, float("nan"), float("inf"), 0.001])
def test_contracargo_sin_monto_valido_avisa_y_no_revoca(client, api_mp, avisos, acreditada, monto):
    contracargo = _contracargo()
    if monto == "sin":
        del contracargo["amount"]
    else:
        contracargo["amount"] = monto
    api_mp.contracargos[CONTRACARGO] = contracargo

    _sin_efecto(acreditada, avisos, _notificar_contracargo(client))


@pytest.mark.parametrize("respuesta", [[], "texto", None, 42])
def test_contracargo_con_respuesta_que_no_es_objeto_avisa_y_no_revoca(client, api_mp, avisos, acreditada, respuesta):
    api_mp.contracargos[CONTRACARGO] = respuesta

    _sin_efecto(acreditada, avisos, _notificar_contracargo(client))


def test_contracargo_con_json_que_no_es_objeto_en_la_api_real_avisa_y_200(
    client, avisos, acreditada, transporte, monkeypatch,
):
    """Sin doblar `obtener_contracargo`: `_pedir` levanta `MPError` con el status
    2xx de una respuesta que MP sí dio. Eso es definitivo, no transitorio."""
    def respondio_mal(*a, **k):
        raise mercadopago_api.MPError("Mercado Pago devolvió JSON que no es un objeto", status=200)

    monkeypatch.setattr(mercadopago_api, "_pedir", respondio_mal)

    _sin_efecto(acreditada, avisos, _notificar_contracargo(client))


@pytest.mark.parametrize("cid", ["../payments/1", "a b", "1;2", "ñ"])
def test_contracargo_con_id_invalido_avisa_y_200(client, avisos, acreditada, transporte, monkeypatch, cid):
    llamadas: list = []
    monkeypatch.setattr(mercadopago_api, "_pedir", lambda *a, **k: llamadas.append(a))

    r = _notificar_contracargo(client, cid=cid)

    assert r.status_code == 200
    assert llamadas == []
    assert not Disputa.objects.exists() and _restante(acreditada) == 1
    assert len(avisos) == 1 and "revisar a mano" in avisos[0]


@pytest.mark.parametrize("error", [
    mercadopago_api.MPError("Mercado Pago no contestó (ReadTimeout)"),
    mercadopago_api.MPError("Mercado Pago respondió 503", status=503),
    mercadopago_api.MPError("Mercado Pago respondió 404", status=404),
    mercadopago_api.MPNoConfigurado("MP_ACCESS_TOKEN no está configurado"),
])
def test_contracargo_con_mp_fallando_sigue_siendo_500(client, avisos, acreditada, transporte, monkeypatch, error):
    def falla(*a, **k):
        raise error

    monkeypatch.setattr(mercadopago_api, "_pedir", falla)

    assert _notificar_contracargo(client).status_code == 500
    assert not Disputa.objects.exists()
