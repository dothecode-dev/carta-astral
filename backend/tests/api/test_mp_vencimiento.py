"""RF13: el cron que vence los checkouts de MP. Reloj fijo: `ahora` se pasa."""

import datetime as dt

import pytest
from django.core.management import call_command

from api import cobro
from api.models import Chart, Interpretation, PasarelaCheckout
from api.pasarelas import mercadopago, mercadopago_api
from api.pasarelas.mercadopago_api import MPError
from api.sujetos import sujeto_natal

pytestmark = pytest.mark.django_db

AHORA = dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.UTC)
VIEJA = AHORA - dt.timedelta(hours=3)  # pasó 1 h + 30 min
PAGO = 777


@pytest.fixture(autouse=True)
def _sin_efectos(monkeypatch):
    monkeypatch.setattr(cobro.analitica, "evento", lambda *a, **k: None)
    monkeypatch.setattr(cobro.notificaciones, "notificar", lambda *a, **k: None)


@pytest.fixture
def avisos(monkeypatch):
    enviados = []
    monkeypatch.setattr(cobro, "avisar_admin", enviados.append)
    return enviados


@pytest.fixture
def mp(monkeypatch):
    """`mp.busquedas[checkout_id] = [pagos]` (o una excepción); `mp.pagos[id]`."""

    class _MP:
        busquedas: dict = {}
        pagos: dict = {}
        buscados: list = []

    m = _MP()
    m.busquedas, m.pagos, m.buscados = {}, {}, []

    def buscar(ref):
        m.buscados.append(ref)
        r = m.busquedas.get(ref, [])
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(mercadopago_api, "buscar_pagos", buscar)
    monkeypatch.setattr(mercadopago_api, "obtener_pago", lambda pid: m.pagos[pid])
    return m


def _fila(n="a", creada=VIEJA, **campos) -> PasarelaCheckout:
    datos = dict(
        checkout_id="mp_" + n * 32, codigo_producto="informe_natal", moneda="ars",
        pasarela=PasarelaCheckout.MERCADOPAGO, precio_centavos=2_500_000, locale="es",
    )
    datos.update(campos)
    fila = PasarelaCheckout.objects.create(**datos)
    PasarelaCheckout.objects.filter(pk=fila.pk).update(created_at=creada)
    fila.refresh_from_db()
    return fila


def _anonima(make_chart, n="a", **campos) -> PasarelaCheckout:
    return _fila(
        n, anonimo=True, account=None, nonce_hash="x" * 64, mail_comprador="ana@example.com",
        sujeto=sujeto_natal(make_chart(account=None)), **campos,
    )


def _pago(fila, status="approved", pago_id=PAGO):
    return {
        "id": pago_id, "status": status, "status_detail": "x", "currency_id": "ARS",
        "transaction_amount": 25000.0, "external_reference": fila.checkout_id,
        "payment_type_id": "account_money", "refunds": [],
    }


def test_sin_pagos_vence(mp, make_account):
    fila = _fila(account=make_account())

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.vencido_at == AHORA
    assert r == {"acreditadas": 0, "vencidas": 1, "esperando": 0, "descartadas": 0}


def test_con_pago_aprobado_acredita(mp, make_account):
    fila = _fila(account=make_account())
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.acreditado_at is not None and fila.vencido_at is None
    assert r == {"acreditadas": 1, "vencidas": 0, "esperando": 0, "descartadas": 0}


@pytest.mark.parametrize("status", ["pending", "in_process"])
def test_con_pago_pendiente_no_vence(mp, make_account, status):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila, status=status)]

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.vencido_at is None and fila.acreditado_at is None
    assert r["esperando"] == 1 and r["vencidas"] == 0


def test_con_pago_rechazado_vence(mp, make_account):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila, status="rejected")]

    assert mercadopago.revisar_vencidas(AHORA)["vencidas"] == 1


def test_no_revisa_lo_que_todavia_no_pasó_el_margen(mp, make_account):
    _fila(account=make_account(), creada=AHORA - dt.timedelta(minutes=89))

    r = mercadopago.revisar_vencidas(AHORA)

    assert mp.buscados == [] and r["vencidas"] == 0


def test_anonima_vencida_hace_menos_de_24h_conserva_la_carta(mp, make_chart):
    fila = _anonima(make_chart, vencido_at=AHORA - dt.timedelta(hours=23))
    carta_id = fila.sujeto.natal_de_id

    r = mercadopago.revisar_vencidas(AHORA)

    assert Chart.objects.filter(pk=carta_id).exists() and r["descartadas"] == 0


def test_anonima_recien_vencida_conserva_la_carta(mp, make_chart):
    fila = _anonima(make_chart)
    carta_id = fila.sujeto.natal_de_id

    r = mercadopago.revisar_vencidas(AHORA)

    assert r["vencidas"] == 1 and r["descartadas"] == 0
    assert Chart.objects.filter(pk=carta_id).exists()


def test_anonima_vencida_hace_mas_de_24h_se_descarta(mp, make_chart):
    fila = _anonima(make_chart, vencido_at=AHORA - dt.timedelta(hours=25))
    carta_id = fila.sujeto.natal_de_id

    r = mercadopago.revisar_vencidas(AHORA)

    assert not Chart.objects.filter(pk=carta_id).exists()
    assert r == {"acreditadas": 0, "vencidas": 0, "esperando": 0, "descartadas": 1}


def test_pago_tardio_antes_de_24h_genera_el_informe_de_su_carta(mp, make_chart, sin_hilo):
    fila = _anonima(make_chart, vencido_at=AHORA - dt.timedelta(hours=2))
    carta_id = fila.sujeto.natal_de_id
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert r["acreditadas"] == 1 and fila.acreditado_at is not None
    assert Chart.objects.filter(pk=carta_id).exists()
    assert len(sin_hilo) == 1 and Interpretation.objects.filter(sujeto__natal_de_id=carta_id).exists()


def test_filas_de_stripe_no_se_tocan(mp, make_account):
    fila = _fila(account=make_account(), pasarela=PasarelaCheckout.STRIPE)

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.vencido_at is None and mp.buscados == []
    assert r["vencidas"] == 0


def test_error_de_mp_en_una_fila_no_corta_las_demas(mp, make_account):
    mala = _fila("a", account=make_account(), creada=VIEJA - dt.timedelta(minutes=1))
    buena = _fila("b", account=make_account())
    mp.busquedas[mala.checkout_id] = MPError("boom", status=500)

    r = mercadopago.revisar_vencidas(AHORA)

    mala.refresh_from_db(), buena.refresh_from_db()
    assert mala.vencido_at is None and buena.vencido_at == AHORA
    assert r["vencidas"] == 1


def test_error_de_mp_con_carta_por_descartar_no_descarta_y_avisa(mp, make_chart, avisos):
    fila = _anonima(make_chart, vencido_at=AHORA - dt.timedelta(hours=30))
    carta_id = fila.sujeto.natal_de_id
    mp.busquedas[fila.checkout_id] = MPError("boom", status=500)

    r = mercadopago.revisar_vencidas(AHORA)

    assert Chart.objects.filter(pk=carta_id).exists() and r["descartadas"] == 0
    assert len(avisos) == 1 and fila.checkout_id in avisos[0]


def test_error_de_mp_sin_carta_por_descartar_no_avisa(mp, make_account, avisos):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = MPError("boom")

    mercadopago.revisar_vencidas(AHORA)

    assert avisos == []


def test_el_comando_imprime_el_resumen(mp, make_account, capsys):
    _fila(account=make_account(), creada=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))

    call_command("vencer_checkouts")

    assert "'vencidas': 1" in capsys.readouterr().out
