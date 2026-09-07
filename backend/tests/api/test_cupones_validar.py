"""`cupones.validar`: la puerta que decide si un cupón sirve para un producto.

Sin HTTP. Los motivos son tipados porque el front los traduce, y porque
`inexistente` e `inactivo` tienen que responderse igual hacia afuera (no se
revela si un código existe).
"""
import datetime as dt

import pytest

from api import cupones
from api.models import Account, Cupon, CuponUso

pytestmark = pytest.mark.django_db


def nuevo(**campos):
    base = dict(codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=2)
    base.update(campos)
    return Cupon.objects.create(**base)


def motivo(codigo, producto="informe_natal", account=None, ahora=None):
    with pytest.raises(cupones.CuponInvalido) as e:
        cupones.validar(codigo, producto, account=account, ahora=ahora)
    return e.value.motivo


def test_un_cupon_vigente_para_ese_producto_vale():
    c = nuevo()
    assert cupones.validar("promo30", "informe_natal") == c


def test_se_busca_sin_importar_mayusculas_ni_espacios():
    nuevo()
    assert cupones.validar("  promo30 ", "informe_natal").codigo == "PROMO30"


def test_un_codigo_que_no_existe_no_vale():
    assert motivo("NADA") == "inexistente"


def test_un_cupon_desactivado_no_vale():
    nuevo(activo=False)
    assert motivo("PROMO30") == "inactivo"


def test_un_cupon_vencido_no_vale():
    nuevo(vence_el=dt.date(2026, 9, 12))
    assert motivo("PROMO30", ahora=dt.datetime(2026, 9, 13, 12, 0, tzinfo=dt.timezone.utc)) == "vencido"
    assert cupones.validar("PROMO30", "informe_natal", ahora=dt.datetime(2026, 9, 12, 12, 0, tzinfo=dt.timezone.utc))


def test_un_producto_que_no_abarca_no_aplica():
    nuevo()
    assert motivo("PROMO30", producto="pack_5_natal") == "no_aplica"


def test_agotado_cuando_los_usos_confirmados_llegan_al_tope():
    c = nuevo(usos_maximos=1)
    CuponUso.objects.create(cupon=c, codigo_producto="informe_natal", descuento_centavos=870,
                            monto_pagado_centavos=2030, external_id="stripe:session:a")
    assert motivo("PROMO30") == "agotado"


def test_una_cuenta_no_usa_dos_veces_el_mismo_cupon():
    c = nuevo()
    acc = Account.objects.create(email="u@x.com")
    CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                            descuento_centavos=870, monto_pagado_centavos=2030,
                            external_id="stripe:session:b")
    assert motivo("PROMO30", account=acc) == "ya_usado"
    otra = Account.objects.create(email="o@x.com")
    assert cupones.validar("PROMO30", "informe_natal", account=otra) == c


def test_el_motivo_publico_no_distingue_inexistente_de_inactivo():
    nuevo(activo=False)
    assert cupones.motivo_publico("inactivo") == cupones.motivo_publico("inexistente")
    assert cupones.motivo_publico("agotado") == "agotado"
