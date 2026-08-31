import pytest

from api.canje import canjear, devolver, otorgar
from api.models import Derecho, Movimiento

pytestmark = pytest.mark.django_db


def test_devolver_repone_el_derecho_y_desvincula_la_carta(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    carta = make_chart(account=cuenta)
    canjear(cuenta, "leer_informe", carta)

    assert devolver(cuenta, "informe_natal", external_id="informe:7:devolucion", chart=carta) is True

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1
    assert Movimiento.objects.filter(tipo="devolucion").count() == 1


def test_devolver_dos_veces_con_el_mismo_external_id_repone_una_sola(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:2")
    carta = make_chart(account=cuenta)
    canjear(cuenta, "leer_informe", carta)
    devolver(cuenta, "informe_natal", external_id="informe:8:devolucion", chart=carta)

    assert devolver(cuenta, "informe_natal", external_id="informe:8:devolucion", chart=carta) is False

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1


def test_tras_devolver_la_carta_vuelve_a_poder_canjearse(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:3")
    carta = make_chart(account=cuenta)
    canjear(cuenta, "leer_informe", carta)
    devolver(cuenta, "informe_natal", external_id="informe:9:devolucion", chart=carta)

    canjear(cuenta, "leer_informe", carta)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="consumo").count() == 2
