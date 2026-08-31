import pytest

from api.canje import SinDerecho, canjear, otorgar
from api.models import Derecho, Movimiento

pytestmark = pytest.mark.django_db


def test_canjear_descuenta_uno_y_deja_el_movimiento_atado_a_la_carta(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    carta = make_chart(account=cuenta)

    _, codigo = canjear(cuenta, "leer_informe", carta)

    assert codigo == "informe_natal"
    assert Derecho.objects.get(account=cuenta, codigo_producto="informe_natal").cantidad_restante == 0
    mov = Movimiento.objects.get(tipo="consumo")
    assert (mov.cantidad, mov.chart_id, mov.codigo_producto) == (-1, carta.id, "informe_natal")


def test_sin_derecho_falla_y_no_toca_el_otro_producto(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "lectura_breve", 3, origen="regalo")
    carta = make_chart(account=cuenta)

    with pytest.raises(SinDerecho) as exc:
        canjear(cuenta, "leer_informe", carta)

    assert exc.value.capacidad == "leer_informe"
    assert Derecho.objects.get(codigo_producto="lectura_breve").cantidad_restante == 3


def test_lo_que_build_construye_se_devuelve_y_queda_en_la_misma_transaccion(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:2")
    carta = make_chart(account=cuenta)
    centinela = object()

    obj, _ = canjear(cuenta, "leer_informe", carta, build=lambda: centinela)

    assert obj is centinela


def test_canjear_de_nuevo_sobre_una_carta_ya_canjeada_no_consume_ni_duplica(make_account, make_chart):
    # El caso que en la v1 de la spec se comía la plata: alguien PAGA por una
    # carta que ya estaba ampliada (dos pestañas, o usó el pack mientras el
    # checkout estaba abierto). El derecho vuelve al saldo, no se evapora.
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:3")
    carta = make_chart(account=cuenta)
    canjear(cuenta, "leer_informe", carta)

    canjear(cuenta, "leer_informe", carta)

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 1
    assert Movimiento.objects.filter(tipo="consumo").count() == 1


def test_la_misma_capacidad_sobre_otra_carta_si_consume(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:4")
    canjear(cuenta, "leer_informe", make_chart(account=cuenta))

    canjear(cuenta, "leer_informe", make_chart(account=cuenta))

    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="consumo").count() == 2
