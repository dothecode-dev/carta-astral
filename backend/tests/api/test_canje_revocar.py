import pytest
from django.test import override_settings

from api.canje import canjear, otorgar, revocar
from api.models import Derecho, Movimiento

pytestmark = pytest.mark.django_db


def test_revocar_lo_no_canjeado_baja_el_saldo_y_no_deja_deuda(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")

    assert revocar(cuenta, "informe_natal", 1, external_id="polar:refund:1") is True

    cuenta.refresh_from_db()
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert (cuenta.deuda, cuenta.refund_count) == (0, 1)


def test_revocar_algo_ya_canjeado_deja_deuda_y_no_toca_el_informe(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:2")
    carta = make_chart(account=cuenta)
    canjear(cuenta, "leer_informe", carta)

    revocar(cuenta, "informe_natal", 1, external_id="polar:refund:2")

    cuenta.refresh_from_db()
    assert cuenta.deuda == 1
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    # El texto entregado se queda con quien lo leyó.
    assert Movimiento.objects.filter(tipo="consumo", chart=carta).exists()


def test_reembolso_parcial_de_un_pack_revoca_lo_no_usado(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "pack_5_natal", 1, origen="compra", external_id="p:3")
    for _ in range(2):
        canjear(cuenta, "leer_informe", make_chart(account=cuenta))

    revocar(cuenta, "informe_natal", 3, external_id="polar:refund:3")

    cuenta.refresh_from_db()
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert cuenta.deuda == 0


def test_el_mismo_external_id_no_revoca_dos_veces(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:4")
    revocar(cuenta, "informe_natal", 1, external_id="polar:refund:4")

    assert revocar(cuenta, "informe_natal", 1, external_id="polar:refund:4") is False

    cuenta.refresh_from_db()
    assert (Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante, cuenta.refund_count) == (1, 1)


@override_settings(REFUND_FLAG_THRESHOLD=2)
def test_al_cruzar_el_umbral_la_cuenta_queda_marcada(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:5")
    revocar(cuenta, "informe_natal", 1, external_id="polar:refund:5")
    revocar(cuenta, "informe_natal", 1, external_id="polar:refund:6")

    cuenta.refresh_from_db()
    assert cuenta.flagged is True


def test_revocar_sobre_una_cuenta_borrada_registra_y_no_explota():
    # Chargeback meses después, con la cuenta ya borrada (spec RF22).
    assert revocar(None, "informe_natal", 1, external_id="polar:refund:7") is True
    assert Movimiento.objects.get(external_id="polar:refund:7").account_id is None
