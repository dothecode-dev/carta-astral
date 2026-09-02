import pytest

from api.canje import otorgar
from api.models import Derecho, Movimiento

pytestmark = pytest.mark.django_db


def test_otorgar_crea_el_derecho_y_su_movimiento(make_account):
    cuenta = make_account()

    assert otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:1") is True

    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 1
    mov = Movimiento.objects.get(account=cuenta)
    assert (mov.tipo, mov.cantidad, mov.origen) == ("otorgamiento", 1, "compra")


def test_otorgar_dos_veces_suma_sobre_el_mismo_derecho(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:1")
    otorgar(cuenta, "informe_natal", 5, origen="compra", external_id="polar:2")

    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 6


def test_el_mismo_external_id_no_otorga_dos_veces(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:1")

    assert otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:1") is False
    assert Derecho.objects.get(account=cuenta).cantidad_restante == 1
    assert Movimiento.objects.count() == 1


def test_un_otorgamiento_cancela_la_deuda_antes_de_dar_saldo(make_account):
    cuenta = make_account()
    cuenta.deuda = 1
    cuenta.save(update_fields=["deuda"])

    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:2")

    cuenta.refresh_from_db()
    assert cuenta.deuda == 0
    assert Derecho.objects.get(account=cuenta).cantidad_restante == 0


def test_si_la_deuda_es_mayor_que_lo_otorgado_queda_deuda_y_cero_saldo(make_account):
    cuenta = make_account()
    cuenta.deuda = 3
    cuenta.save(update_fields=["deuda"])

    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="polar:3")

    cuenta.refresh_from_db()
    assert cuenta.deuda == 2
    assert Derecho.objects.get(account=cuenta).cantidad_restante == 0


def test_otorgar_un_producto_de_acceso_pone_vigencia_y_no_cantidad(make_account, monkeypatch):
    from api import catalogo
    plan = catalogo.Producto(
        codigo="plan_demo", precio_centavos=999, naturaleza=catalogo.ACCESO,
        capacidades=("leer_informe",), otorga=(("plan_demo", 1),), duracion_dias=30,
    )
    monkeypatch.setitem(catalogo.CATALOGO, "plan_demo", plan)
    cuenta = make_account()

    otorgar(cuenta, "plan_demo", 1, origen="compra", external_id="polar:4")

    d = Derecho.objects.get(account=cuenta, codigo_producto="plan_demo")
    assert d.cantidad_restante is None and d.vigente_hasta is not None


def test_no_se_puede_otorgar_un_producto_que_no_esta_en_el_catalogo(make_account):
    with pytest.raises(KeyError, match="pack_100"):
        otorgar(make_account(), "pack_100", 1, origen="compra")
