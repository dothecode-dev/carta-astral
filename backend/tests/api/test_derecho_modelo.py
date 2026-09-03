import pytest
from django.db import IntegrityError
from django.utils import timezone

from api.models import Derecho, Movimiento

pytestmark = pytest.mark.django_db


def test_un_derecho_consumible_guarda_cantidad_y_no_vigencia(make_account):
    d = Derecho.objects.create(account=make_account(), codigo_producto="informe_natal", cantidad_restante=2)
    assert (d.cantidad_restante, d.vigente_hasta) == (2, None)


def test_un_derecho_de_acceso_guarda_vigencia_y_no_cantidad(make_account):
    hasta = timezone.now() + timezone.timedelta(days=30)
    d = Derecho.objects.create(account=make_account(), codigo_producto="plan_demo", vigente_hasta=hasta)
    assert d.cantidad_restante is None


def test_no_se_puede_mezclar_cantidad_y_vigencia(make_account):
    with pytest.raises(IntegrityError):
        Derecho.objects.create(
            account=make_account(), codigo_producto="informe_natal",
            cantidad_restante=1, vigente_hasta=timezone.now(),
        )


def test_no_se_puede_no_tener_ni_cantidad_ni_vigencia(make_account):
    with pytest.raises(IntegrityError):
        Derecho.objects.create(account=make_account(), codigo_producto="informe_natal")


def test_la_cantidad_nunca_es_negativa(make_account):
    # La deuda vive en Account.deuda, no acá: saldo y deuda no son el mismo
    # número (spec RF5/RF6, hallazgo de la critique).
    with pytest.raises(IntegrityError):
        Derecho.objects.create(
            account=make_account(), codigo_producto="informe_natal", cantidad_restante=-1
        )


def test_una_cuenta_tiene_un_solo_derecho_por_producto(make_account):
    cuenta = make_account()
    Derecho.objects.create(account=cuenta, codigo_producto="informe_natal", cantidad_restante=1)
    with pytest.raises(IntegrityError):
        Derecho.objects.create(account=cuenta, codigo_producto="informe_natal", cantidad_restante=1)


def test_la_cuenta_arranca_sin_deuda(make_account):
    assert make_account().deuda == 0


def test_dos_movimientos_no_comparten_external_id(make_account):
    cuenta = make_account()
    Movimiento.objects.create(
        account=cuenta, codigo_producto="informe_natal", tipo="otorgamiento",
        cantidad=1, origen="compra", external_id="stripe:evt_1",
    )
    with pytest.raises(IntegrityError):
        Movimiento.objects.create(
            account=cuenta, codigo_producto="informe_natal", tipo="otorgamiento",
            cantidad=1, origen="compra", external_id="stripe:evt_1",
        )


def test_varios_movimientos_pueden_no_tener_external_id(make_account):
    cuenta = make_account()
    for _ in range(2):
        Movimiento.objects.create(
            account=cuenta, codigo_producto="lectura_breve", tipo="consumo",
            cantidad=-1, origen="regalo",
        )
    assert Movimiento.objects.filter(codigo_producto="lectura_breve").count() == 2
