import pytest
from django.utils import timezone

from api.canje import derechos_de, otorgar, puede
from api.models import Derecho

pytestmark = pytest.mark.django_db


def test_sin_derechos_no_puede_nada(make_account):
    cuenta = make_account()
    assert puede(cuenta, "leer_informe") is False
    assert puede(cuenta, "leer_breve") is False


def test_con_saldo_puede(make_account):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    assert puede(cuenta, "leer_informe") is True


def test_con_saldo_en_cero_no_puede(make_account):
    cuenta = make_account()
    Derecho.objects.create(account=cuenta, codigo_producto="informe_natal", cantidad_restante=0)
    assert puede(cuenta, "leer_informe") is False


def test_el_derecho_de_un_producto_no_habilita_la_capacidad_del_otro(make_account):
    cuenta = make_account()
    otorgar(cuenta, "lectura_breve", 3, origen="regalo")
    assert puede(cuenta, "leer_breve") is True
    assert puede(cuenta, "leer_informe") is False


def test_dos_productos_dan_la_misma_capacidad_y_basta_uno(make_account):
    # pack_5_natal otorga derechos de informe_natal: la capacidad la habilita
    # el derecho resultante, no el producto que se compró.
    cuenta = make_account()
    otorgar(cuenta, "pack_5_natal", 1, origen="compra", external_id="p:2")
    assert puede(cuenta, "leer_informe") is True


def test_un_acceso_vigente_puede_y_uno_vencido_no(make_account, monkeypatch):
    from api import catalogo
    monkeypatch.setitem(catalogo.CATALOGO, "plan_demo", catalogo.Producto(
        codigo="plan_demo", precio_centavos=999, naturaleza=catalogo.ACCESO,
        capacidades=("horoscopo_semanal",), otorga=("plan_demo", 1), duracion_dias=30,
    ))
    cuenta = make_account()
    d = Derecho.objects.create(
        account=cuenta, codigo_producto="plan_demo",
        vigente_hasta=timezone.now() + timezone.timedelta(days=1),
    )
    assert puede(cuenta, "horoscopo_semanal") is True

    d.vigente_hasta = timezone.now() - timezone.timedelta(seconds=1)
    d.save(update_fields=["vigente_hasta"])
    assert puede(cuenta, "horoscopo_semanal") is False


def test_derechos_de_devuelve_lo_que_el_endpoint_necesita(make_account):
    cuenta = make_account()
    otorgar(cuenta, "lectura_breve", 3, origen="regalo")
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:3")

    assert derechos_de(cuenta) == [
        {"codigo_producto": "informe_natal", "cantidad_restante": 1, "vigente_hasta": None},
        {"codigo_producto": "lectura_breve", "cantidad_restante": 3, "vigente_hasta": None},
    ]
