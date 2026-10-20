"""RF13: el cron que vence los checkouts de MP. Reloj fijo: `ahora` se pasa."""

import datetime as dt

import pytest
from django.core.management import call_command

from api import cobro, compra_anonima
from api.models import Chart, Derecho, Interpretation, PasarelaCheckout
from api.pasarelas import mercadopago, mercadopago_api, mercadopago_cron
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


@pytest.fixture(autouse=True)
def ventas(monkeypatch):
    """El aviso de venta en pesos va por su canal (ver test_mp_webhook_pago)."""
    enviadas = []
    monkeypatch.setattr(cobro, "avisar_venta", enviadas.append)
    return enviadas


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
    monkeypatch.setattr(mercadopago_api, "buscar_pagos_actualizados", lambda desde, hasta: [])
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
    datos = dict(
        anonimo=True, account=None, nonce_hash="x" * 64, mail_comprador="ana@example.com",
        sujeto=sujeto_natal(make_chart(account=None)),
    )
    datos.update(campos)
    return _fila(n, **datos)


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
    assert fila.vencido_at == AHORA and fila.mp_revisado_at == AHORA
    assert r == {"acreditadas": 0, "vencidas": 1, "esperando": 0, "descartadas": 0}


def test_con_pago_aprobado_acredita(mp, make_account):
    fila = _fila(account=make_account())
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.acreditado_at is not None and fila.vencido_at is None
    assert r == {"acreditadas": 1, "vencidas": 0, "esperando": 0, "descartadas": 0}


@pytest.mark.parametrize("status", ["pending", "in_process", "authorized", "in_mediation"])
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


def test_filas_de_stripe_no_se_tocan(mp, make_account, make_chart):
    abierta = _fila("a", account=make_account(), pasarela=PasarelaCheckout.STRIPE, moneda="usd")
    pagada = _fila(
        "b", account=make_account(), pasarela=PasarelaCheckout.STRIPE, moneda="usd",
        acreditado_at=VIEJA, pago_id="pi_1",
    )
    anonima = _anonima(
        make_chart, "c", pasarela=PasarelaCheckout.STRIPE, moneda="usd", vencido_at=AHORA - dt.timedelta(hours=30),
    )
    carta_id = anonima.sujeto.natal_de_id

    r = mercadopago.revisar_vencidas(AHORA)

    for fila in (abierta, pagada, anonima):
        fila.refresh_from_db()
        assert fila.mp_revisado_at is None
    assert abierta.vencido_at is None and mp.buscados == []
    assert Chart.objects.filter(pk=carta_id).exists()
    assert r == {"acreditadas": 0, "vencidas": 0, "esperando": 0, "descartadas": 0}


def test_error_de_mp_en_una_fila_no_corta_las_demas(mp, make_account):
    mala = _fila("a", account=make_account(), creada=VIEJA - dt.timedelta(minutes=1))
    buena = _fila("b", account=make_account())
    mp.busquedas[mala.checkout_id] = MPError("boom", status=500)

    r = mercadopago.revisar_vencidas(AHORA)

    mala.refresh_from_db(), buena.refresh_from_db()
    assert mala.vencido_at is None and buena.vencido_at == AHORA
    assert r["vencidas"] == 1


def test_error_de_mp_con_carta_por_descartar_no_descarta_ni_cierra(mp, make_chart, avisos):
    """Transitorio: la fila queda abierta y se reintenta; sin aviso por corrida."""
    fila = _anonima(make_chart, vencido_at=AHORA - dt.timedelta(hours=30))
    carta_id = fila.sujeto.natal_de_id
    mp.busquedas[fila.checkout_id] = MPError("boom", status=500)

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert Chart.objects.filter(pk=carta_id).exists() and r["descartadas"] == 0
    assert fila.mp_revisado_at is None and avisos == []


def test_error_de_mp_sin_carta_por_descartar_no_avisa(mp, make_account, avisos):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = MPError("boom")

    mercadopago.revisar_vencidas(AHORA)

    assert avisos == []


def test_el_comando_imprime_el_resumen(mp, make_account, capsys):
    _fila(account=make_account(), creada=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))

    call_command("vencer_checkouts")

    assert "'vencidas': 1" in capsys.readouterr().out


def test_pendiente_en_una_corrida_y_aprobado_en_la_siguiente_acredita(mp, make_account):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila, status="pending")]
    assert mercadopago.revisar_vencidas(AHORA)["esperando"] == 1

    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]
    r = mercadopago.revisar_vencidas(AHORA + dt.timedelta(minutes=15))

    fila.refresh_from_db()
    assert r["acreditadas"] == 1 and fila.acreditado_at is not None
    assert Derecho.objects.filter(account=fila.account).exists()


def test_fila_ya_revisada_no_se_busca_de_nuevo(mp, make_account):
    _fila(account=make_account(), vencido_at=AHORA - dt.timedelta(hours=5), mp_revisado_at=AHORA - dt.timedelta(hours=5))

    mercadopago.revisar_vencidas(AHORA)

    assert mp.buscados == []


def test_una_fila_que_falla_al_descartar_no_corta_las_demas(mp, make_chart, make_account, monkeypatch, avisos):
    mala = _anonima(make_chart, "a", vencido_at=AHORA - dt.timedelta(hours=30))
    buena = _fila("b", account=make_account())

    def roto(_checkout_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(compra_anonima, "descartar", roto)

    r = mercadopago.revisar_vencidas(AHORA)

    buena.refresh_from_db()
    assert buena.vencido_at == AHORA and r["vencidas"] == 1
    assert mala.checkout_id in mp.buscados
    assert len(avisos) == 1 and mala.checkout_id in avisos[0]


def test_sin_token_aborta_la_corrida(monkeypatch, make_account):
    _fila(account=make_account())

    def sin_token(_ref):
        raise mercadopago_api.MPNoConfigurado("falta")

    monkeypatch.setattr(mercadopago_api, "buscar_pagos", sin_token)

    with pytest.raises(mercadopago_api.MPNoConfigurado):
        mercadopago.revisar_vencidas(AHORA)


def test_sin_token_al_procesar_un_pago_aprobado_aborta(mp, make_account, monkeypatch):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    def sin_token(_pid):
        raise mercadopago_api.MPNoConfigurado("falta")

    monkeypatch.setattr(mercadopago_cron, "procesar_pago", sin_token)

    with pytest.raises(mercadopago_api.MPNoConfigurado):
        mercadopago.revisar_vencidas(AHORA)


# --- Ruling 12: cada fila de MP se revisa hasta cerrarla, una sola vez ------------------


@pytest.fixture
def reembolsos(monkeypatch):
    pedidos = []
    monkeypatch.setattr(mercadopago_api, "reembolsar", lambda pid, clave: pedidos.append(pid) or {"id": 1})
    return pedidos


def test_fila_acreditada_con_un_duplicado_perdido_lo_reembolsa_avisa_y_cierra(mp, make_account, avisos, reembolsos):
    fila = _fila(account=make_account(), acreditado_at=VIEJA, pago_id=str(PAGO))
    duplicado = _pago(fila, pago_id=888)
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.pagos["888"] = duplicado
    mp.busquedas[fila.checkout_id] = [_pago(fila), duplicado]

    mercadopago.revisar_vencidas(AHORA)
    mercadopago.revisar_vencidas(AHORA + dt.timedelta(minutes=15))

    fila.refresh_from_db()
    assert reembolsos == ["888"]
    assert len(avisos) == 1 and "888" in avisos[0] and "DUPLICADO" in avisos[0]
    assert fila.mp_revisado_at == AHORA and fila.vencido_at is None and fila.pago_id == str(PAGO)
    assert mp.buscados == [fila.checkout_id]


def test_fila_acreditada_sin_duplicados_se_cierra_sin_avisos(mp, make_account, avisos, reembolsos):
    fila = _fila(account=make_account(), acreditado_at=VIEJA, pago_id=str(PAGO))
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    r = mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.mp_revisado_at == AHORA and fila.vencido_at is None
    assert avisos == [] and reembolsos == []
    assert r == {"acreditadas": 0, "vencidas": 0, "esperando": 0, "descartadas": 0}


def test_pago_aprobado_que_no_se_puede_acreditar_avisa_una_sola_vez(mp, make_account, avisos):
    fila = _fila(account=make_account())
    otro_monto = {**_pago(fila), "transaction_amount": 1.0}
    mp.pagos[str(PAGO)] = otro_monto
    mp.busquedas[fila.checkout_id] = [otro_monto]

    mercadopago.revisar_vencidas(AHORA)
    mercadopago.revisar_vencidas(AHORA + dt.timedelta(minutes=15))

    fila.refresh_from_db()
    assert len(avisos) == 1 and "no coincide" in avisos[0]
    assert fila.acreditado_at is None and fila.mp_revisado_at == AHORA
    # Hubo plata: no es una fila vencida, no se lista como tal ni se descarta su carta.
    assert fila.vencido_at is None


def test_pendiente_mantiene_abierta_y_cierra_al_acreditar(mp, make_account):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila, status="pending")]
    assert mercadopago.revisar_vencidas(AHORA)["esperando"] == 1
    assert mercadopago.revisar_vencidas(AHORA + dt.timedelta(minutes=15))["esperando"] == 1
    fila.refresh_from_db()
    assert fila.mp_revisado_at is None and fila.vencido_at is None

    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]
    cierre = AHORA + dt.timedelta(minutes=30)
    assert mercadopago.revisar_vencidas(cierre)["acreditadas"] == 1
    mercadopago.revisar_vencidas(cierre + dt.timedelta(minutes=15))

    fila.refresh_from_db()
    assert fila.acreditado_at is not None and fila.mp_revisado_at == cierre and fila.vencido_at is None
    assert mp.buscados == [fila.checkout_id] * 3


def test_error_transitorio_deja_la_fila_abierta_y_se_reintenta(mp, make_account, avisos):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = MPError("boom", status=500)
    mercadopago.revisar_vencidas(AHORA)
    fila.refresh_from_db()
    assert fila.mp_revisado_at is None and fila.vencido_at is None

    mp.busquedas[fila.checkout_id] = []
    mercadopago.revisar_vencidas(AHORA + dt.timedelta(minutes=15))

    fila.refresh_from_db()
    assert fila.mp_revisado_at is not None and fila.vencido_at is not None
    assert avisos == []


def test_fallo_inesperado_al_procesar_deja_la_fila_abierta(mp, make_account, monkeypatch, avisos):
    fila = _fila(account=make_account())
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    def roto(_pid):
        raise RuntimeError("boom")

    monkeypatch.setattr(mercadopago_cron, "procesar_pago", roto)

    mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert fila.mp_revisado_at is None and fila.vencido_at is None and avisos == []


def test_compra_anonima_sin_mail_es_definitiva_cierra_y_no_descarta(mp, make_chart, avisos):
    fila = _anonima(make_chart, mail_comprador="")
    carta_id = fila.sujeto.natal_de_id
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]

    mercadopago.revisar_vencidas(AHORA)
    mercadopago.revisar_vencidas(AHORA + dt.timedelta(hours=30))

    fila.refresh_from_db()
    assert fila.mp_revisado_at == AHORA and fila.vencido_at is None and fila.acreditado_at is None
    assert len(avisos) == 1 and "SIN mail" in avisos[0]
    assert Chart.objects.filter(pk=carta_id).exists()


def test_anonima_cerrada_se_descarta_a_las_24h_sin_volver_a_buscar(mp, make_chart):
    fila = _anonima(make_chart)
    carta_id = fila.sujeto.natal_de_id

    r = mercadopago.revisar_vencidas(AHORA)
    assert r["vencidas"] == 1 and r["descartadas"] == 0
    assert Chart.objects.filter(pk=carta_id).exists()

    r = mercadopago.revisar_vencidas(AHORA + dt.timedelta(hours=25))

    assert r == {"acreditadas": 0, "vencidas": 0, "esperando": 0, "descartadas": 1}
    assert not Chart.objects.filter(pk=carta_id).exists()
    assert mp.buscados == [fila.checkout_id]


def test_fila_acreditada_con_carta_no_reprocesa_el_pago_que_la_acredito(mp, make_account, make_chart, monkeypatch, avisos):
    """Quien acreditó la fila ya procesó ese pago: el cron sólo busca OTROS.
    Reprocesarlo volvería a correr `arrancar_informe` sobre un informe que el
    sistema pudo haber dado por perdido (y devuelto el derecho)."""
    cuenta = make_account()
    fila = _fila(
        account=cuenta, sujeto=sujeto_natal(make_chart(account=cuenta)),
        acreditado_at=VIEJA, pago_id=str(PAGO),
    )
    mp.pagos[str(PAGO)] = _pago(fila)
    mp.busquedas[fila.checkout_id] = [_pago(fila)]
    procesados = []
    monkeypatch.setattr(mercadopago_cron, "procesar_pago", procesados.append)
    acreditados = []
    monkeypatch.setattr(cobro, "acreditar", lambda *a, **k: acreditados.append(a))

    mercadopago.revisar_vencidas(AHORA)

    fila.refresh_from_db()
    assert procesados == [] and acreditados == []
    assert not Interpretation.objects.filter(sujeto=fila.sujeto).exists()
    assert fila.mp_revisado_at == AHORA and avisos == []


# --- code review C (Ruling 15): conciliación de pagos actualizados -----------------------


@pytest.fixture
def actualizados(monkeypatch):
    """`actualizados.pagos` es lo que devuelve la búsqueda por
    `date_last_updated`; `actualizados.ventanas` registra (desde, hasta)."""
    from django.core.cache import cache

    cache.clear()

    class _A:
        pagos: list = []
        ventanas: list = []
        fallo: Exception | None = None

    a = _A()
    a.pagos, a.ventanas = [], []

    def buscar(desde, hasta):
        a.ventanas.append((desde, hasta))
        if a.fallo is not None:
            raise a.fallo
        return a.pagos

    monkeypatch.setattr(mercadopago_api, "buscar_pagos_actualizados", buscar)
    return a


def _actualizado(pago_id, ref, status="refunded", cuando="2026-10-20T08:50:00.000-04:00"):
    return {"id": pago_id, "status": status, "external_reference": ref, "date_last_updated": cuando}


def test_conciliar_aplica_un_reembolso_cuya_notificacion_se_perdio(mp, make_account, avisos, actualizados):
    from api.models import Reembolso

    cuenta = make_account()
    fila = _fila(account=cuenta)
    mp.pagos[str(PAGO)] = _pago(fila)
    mercadopago.procesar_pago(str(PAGO))
    PasarelaCheckout.objects.filter(pk=fila.pk).update(mp_revisado_at=AHORA)
    mp.pagos[str(PAGO)] = {
        **_pago(fila, status="refunded"),
        "refunds": [{"id": 4001, "amount": 25000.0, "status": "approved"}],
    }
    actualizados.pagos = [_actualizado(PAGO, fila.checkout_id)]

    r = mercadopago.conciliar_actualizados(AHORA)

    assert actualizados.ventanas == [(AHORA - dt.timedelta(hours=2), AHORA)]
    assert list(Reembolso.objects.values_list("refund_id", flat=True)) == ["mp:refund:4001"]
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 0
    assert r == {"conciliados": 1, "fallidos": 0}
    assert avisos == []


def test_conciliar_ignora_pagos_ajenos(mp, monkeypatch, actualizados):
    procesados = []
    monkeypatch.setattr(mercadopago_cron, "procesar_pago", procesados.append)
    actualizados.pagos = [
        _actualizado(1, "otra-integracion"), _actualizado(2, "mp_corto"), _actualizado(3, None),
        _actualizado(4, "mp_" + "b" * 32),
    ]

    mercadopago.conciliar_actualizados(AHORA)

    assert procesados == ["4"]


def test_conciliar_un_pago_que_falla_no_corta_los_demas_ni_avisa(mp, monkeypatch, avisos, actualizados):
    procesados = []

    def procesar(pid):
        procesados.append(pid)
        if pid == "1":
            raise RuntimeError("boom")

    monkeypatch.setattr(mercadopago_cron, "procesar_pago", procesar)
    actualizados.pagos = [_actualizado(1, "mp_" + "a" * 32), _actualizado(2, "mp_" + "b" * 32)]

    r = mercadopago.conciliar_actualizados(AHORA)

    assert procesados == ["1", "2"]
    assert r == {"conciliados": 1, "fallidos": 1}
    assert avisos == []


def test_conciliar_procesa_cada_version_de_un_pago_una_vez(mp, monkeypatch, actualizados):
    """La ventana se solapa (2 h, cada 15 min): sin esto un pago en mediación
    avisaría ocho veces. El que falló sí se reintenta en la corrida siguiente,
    y una versión nueva del mismo pago (otro `date_last_updated`) también."""
    procesados = []
    falla = {"2"}

    def procesar(pid):
        procesados.append(pid)
        if pid in falla:
            raise RuntimeError("boom")

    monkeypatch.setattr(mercadopago_cron, "procesar_pago", procesar)
    actualizados.pagos = [_actualizado(1, "mp_" + "a" * 32), _actualizado(2, "mp_" + "b" * 32)]
    mercadopago.conciliar_actualizados(AHORA)
    falla.clear()
    mercadopago.conciliar_actualizados(AHORA + dt.timedelta(minutes=15))
    actualizados.pagos = [_actualizado(1, "mp_" + "a" * 32, cuando="2026-10-20T09:10:00.000-04:00")]
    mercadopago.conciliar_actualizados(AHORA + dt.timedelta(minutes=30))

    assert procesados == ["1", "2", "2", "1"]


def test_conciliar_con_mp_caido_no_levanta_ni_avisa(mp, avisos, actualizados):
    actualizados.fallo = MPError("x", status=503)

    assert mercadopago.conciliar_actualizados(AHORA) == {"conciliados": 0, "fallidos": 0}
    assert avisos == []


def test_conciliar_sin_token_levanta(mp, actualizados):
    actualizados.fallo = mercadopago_api.MPNoConfigurado("falta")

    with pytest.raises(mercadopago_api.MPNoConfigurado):
        mercadopago.conciliar_actualizados(AHORA)


def test_el_comando_tambien_concilia(mp, make_account, capsys, actualizados):
    call_command("vencer_checkouts")

    assert len(actualizados.ventanas) == 1
    assert "'conciliados': 0" in capsys.readouterr().out
