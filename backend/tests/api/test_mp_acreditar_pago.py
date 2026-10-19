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

    _correr("--pasarela", "mercadopago", PAGO)

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
def test_pasarela_stripe_deriva_a_acreditar_sesion(pagos):
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
