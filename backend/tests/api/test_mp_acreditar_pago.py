"""`manage.py acreditar_pago`: la reparación manual de un pago de Mercado Pago (RF14).

Llama a la misma traducción que el webhook (`procesar_pago`), así que una
corrida a mano deja exactamente lo mismo. La API de MP está doblada.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from api import cobro
from api.models import Derecho, Movimiento, PasarelaCheckout
from api.pasarelas import mercadopago_api
from api.pasarelas.mercadopago_api import MPError

CHECKOUT = "mp_" + "b" * 32
PAGO = "184963579792"


@pytest.fixture(autouse=True)
def _sin_efectos(monkeypatch):
    monkeypatch.setattr(cobro, "avisar_admin", lambda *a, **k: None)
    monkeypatch.setattr(cobro.notificaciones, "notificar", lambda *a, **k: None)
    monkeypatch.setattr(cobro.analitica, "evento", lambda *a, **k: None)


@pytest.fixture
def pagos(monkeypatch):
    tabla: dict = {}
    monkeypatch.setattr(mercadopago_api, "obtener_pago", lambda pid: tabla[pid])
    return tabla


def _pago(**campos) -> dict:
    datos = {
        "id": int(PAGO), "status": "approved", "status_detail": "accredited", "currency_id": "ARS",
        "transaction_amount": 25000.0, "external_reference": CHECKOUT, "payment_type_id": "account_money",
        "refunds": [],
    }
    datos.update(campos)
    return datos


def _fila(cuenta) -> PasarelaCheckout:
    return PasarelaCheckout.objects.create(
        checkout_id=CHECKOUT, account=cuenta, codigo_producto="informe_natal",
        pasarela=PasarelaCheckout.MERCADOPAGO, moneda="ars", precio_centavos=2_500_000,
        mp_preferencia_id="pref_1", locale="es",
    )


def _correr(*args) -> str:
    salida = StringIO()
    call_command("acreditar_pago", *args, stdout=salida)
    return salida.getvalue()


@pytest.mark.django_db
def test_acredita_igual_que_el_webhook(pagos, make_account):
    cuenta = make_account()
    fila = _fila(cuenta)
    pagos[PAGO] = _pago()

    salida = _correr("--pasarela", "mercadopago", PAGO)

    assert "acreditado" in salida
    fila.refresh_from_db()
    assert fila.acreditado_at is not None
    assert Derecho.objects.filter(account=cuenta).exists()
    assert Movimiento.objects.filter(account=cuenta, tipo="otorgamiento").count() == 1


@pytest.mark.django_db
def test_dos_corridas_un_movimiento(pagos, make_account):
    cuenta = make_account()
    _fila(cuenta)
    pagos[PAGO] = _pago()

    _correr("--pasarela", "mercadopago", PAGO)
    _correr("--pasarela", "mercadopago", PAGO)

    assert Movimiento.objects.filter(account=cuenta, tipo="otorgamiento").count() == 1


@pytest.mark.django_db
def test_pasarela_stripe_deriva_a_acreditar_sesion():
    with pytest.raises(CommandError, match="acreditar_sesion") as e:
        _correr("--pasarela", "stripe", "cs_test_123")

    assert e.value.returncode == 2


@pytest.mark.django_db
@pytest.mark.parametrize("valor", ["../x", "12 3", "a/b", ""])
def test_id_invalido_no_llama_a_mp(monkeypatch, valor):
    def _no(pid):
        raise AssertionError("no debía llamar a MP")

    monkeypatch.setattr(mercadopago_api, "obtener_pago", _no)

    with pytest.raises(CommandError, match="inválido"):
        _correr("--pasarela", "mercadopago", valor)


@pytest.mark.django_db
def test_fallo_de_mp_sale_con_mensaje_y_no_con_traceback(monkeypatch):
    def _falla(pid):
        raise MPError("timeout", status=None)

    monkeypatch.setattr(mercadopago_api, "obtener_pago", _falla)

    with pytest.raises(CommandError, match="timeout"):
        _correr("--pasarela", "mercadopago", PAGO)


@pytest.mark.django_db
def test_pago_sin_fila_sale_con_mensaje(pagos):
    pagos[PAGO] = _pago()

    with pytest.raises(CommandError, match=CHECKOUT):
        _correr("--pasarela", "mercadopago", PAGO)


@pytest.mark.django_db
def test_pago_pendiente_es_error_con_el_status(pagos, make_account):
    fila = _fila(make_account())
    pagos[PAGO] = _pago(status="pending")

    with pytest.raises(CommandError, match="status=pending"):
        _correr("--pasarela", "mercadopago", PAGO)

    fila.refresh_from_db()
    assert fila.acreditado_at is None


@pytest.mark.django_db
def test_referencia_ajena_es_error(pagos, make_account):
    _fila(make_account())
    pagos[PAGO] = _pago(external_reference="pedido-de-otro-sistema")

    with pytest.raises(CommandError, match="ajena"):
        _correr("--pasarela", "mercadopago", PAGO)


@pytest.mark.django_db
def test_fila_de_otra_pasarela_es_error(pagos, make_account):
    fila = _fila(make_account())
    fila.pasarela = PasarelaCheckout.STRIPE
    fila.save()
    pagos[PAGO] = _pago()

    with pytest.raises(CommandError, match="stripe"):
        _correr("--pasarela", "mercadopago", PAGO)


@pytest.mark.django_db
def test_pago_duplicado_es_error_y_no_dice_acreditado(pagos, make_account, monkeypatch):
    cuenta = make_account()
    _fila(cuenta)
    pagos[PAGO] = _pago()
    _correr("--pasarela", "mercadopago", PAGO)
    otro = "999000111"
    pagos[otro] = _pago(id=int(otro))
    monkeypatch.setattr(mercadopago_api, "reembolsar", lambda pid, key: {"id": 1})

    with pytest.raises(CommandError, match="duplicado") as e:
        _correr("--pasarela", "mercadopago", otro)

    assert Movimiento.objects.filter(account=cuenta, tipo="otorgamiento").count() == 1
    # Si el reembolso se pidió o falló lo dice el aviso de Telegram; el comando
    # no lo sabe y no puede afirmarlo.
    assert "se pidió su reembolso" not in str(e.value)
    assert "reembolso a verificar en MP" in str(e.value)


@pytest.mark.django_db
def test_compra_anonima_sin_mail_explica_que_falta(pagos, make_account, monkeypatch):
    _fila(make_account())
    pagos[PAGO] = _pago()

    def _sin_mail(*a, **k):
        raise cobro.CompraAnonimaSinMail("sin mail")

    monkeypatch.setattr(cobro, "acreditar", _sin_mail)

    with pytest.raises(CommandError, match="sin mail del comprador"):
        _correr("--pasarela", "mercadopago", PAGO)


# --- code review H ------------------------------------------------------------------------


@pytest.mark.django_db
def test_sin_token_sale_con_un_mensaje_claro(settings):
    settings.MP_ACCESS_TOKEN = ""

    with pytest.raises(CommandError, match="MP_ACCESS_TOKEN"):
        _correr("--pasarela", "mercadopago", PAGO)


def _segunda_lectura_falla(monkeypatch, pago):
    leidas = []

    def obtener(pid):
        leidas.append(pid)
        if len(leidas) > 1:
            raise MPError("Mercado Pago no contestó (ReadTimeout)")
        return pago

    monkeypatch.setattr(mercadopago_api, "obtener_pago", obtener)


@pytest.mark.django_db
def test_si_la_relectura_falla_tras_acreditar_informa_desde_la_base(monkeypatch, make_account):
    """Acreditó: la relectura que sólo confirma no puede convertir eso en un
    error que haga creer que no se acreditó."""
    fila = _fila(make_account())
    _segunda_lectura_falla(monkeypatch, _pago())

    salida = _correr("--pasarela", "mercadopago", PAGO)

    fila.refresh_from_db()
    assert fila.acreditado_at is not None
    assert "acreditado" in salida and CHECKOUT in salida


@pytest.mark.django_db
def test_si_la_relectura_falla_sin_acreditar_dice_que_no_se_pudo_confirmar(monkeypatch, make_account):
    _fila(make_account())
    _segunda_lectura_falla(monkeypatch, _pago(status="pending"))

    with pytest.raises(CommandError, match="no quedó acreditado"):
        _correr("--pasarela", "mercadopago", PAGO)
