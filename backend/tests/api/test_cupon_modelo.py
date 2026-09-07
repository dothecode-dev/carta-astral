"""`Cupon` y `CuponUso`: lo que el modelo garantiza antes de que exista
ningún endpoint.

El código se guarda normalizado (Stripe compara sin distinguir mayúsculas y
sólo admite `A-Z0-9-`), el porcentaje vive en 1..100 también en la base, los
productos salen del catálogo, el vencimiento es una fecha en hora de Buenos
Aires, y el uso sobrevive al borrado de la cuenta sin devolver el lugar.
"""
import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from api.models import Account, Cupon, CuponUso


def cupon(**campos):
    base = dict(codigo="PROMO30", porcentaje=30, productos=["informe_natal"], usos_maximos=10)
    base.update(campos)
    c = Cupon(**base)
    c.full_clean()
    c.save()
    return c


@pytest.mark.django_db
@pytest.mark.parametrize("escrito", ["promo30", " Promo30 ", "PROMO30"])
def test_el_codigo_se_guarda_en_mayusculas_y_sin_espacios(escrito):
    assert cupon(codigo=escrito).codigo == "PROMO30"


@pytest.mark.django_db
@pytest.mark.parametrize("escrito", ["PROMO 30", "PROMO_30", "AB", "Ñ-30", "X" * 41])
def test_un_codigo_fuera_del_alfabeto_de_stripe_no_se_guarda(escrito):
    with pytest.raises(ValidationError):
        cupon(codigo=escrito)


@pytest.mark.django_db
def test_el_codigo_es_unico():
    cupon()
    with pytest.raises(ValidationError):
        cupon(codigo="promo30")


@pytest.mark.django_db
@pytest.mark.parametrize("porcentaje", [0, 101])
def test_un_porcentaje_fuera_de_rango_no_pasa_la_validacion(porcentaje):
    with pytest.raises(ValidationError):
        cupon(porcentaje=porcentaje)


@pytest.mark.django_db
def test_el_rango_del_porcentaje_tambien_lo_sostiene_la_base():
    """`full_clean` se puede saltear (un `objects.create` en un shell); la
    CheckConstraint no."""
    with pytest.raises(IntegrityError), transaction.atomic():
        Cupon.objects.create(codigo="RARO", porcentaje=150, productos=["informe_natal"], usos_maximos=1)


@pytest.mark.django_db
@pytest.mark.parametrize(
    "productos", [[], ["no_existe"], ["lectura_breve"], ["informe_natal", "informe_natal"]],
)
def test_los_productos_tienen_que_ser_del_catalogo_con_precio_y_sin_repetir(productos):
    with pytest.raises(ValidationError):
        cupon(productos=productos)


@pytest.mark.django_db
def test_vence_al_final_del_dia_en_buenos_aires():
    """Django corre en UTC. «Vence el 12» tiene que ser el 12 a las 23:59:59
    de Buenos Aires —03:00 del 13 en UTC—, no el 12 a las 21:00."""
    c = cupon(vence_el=dt.date(2026, 9, 12))
    assert c.vence_at == dt.datetime(2026, 9, 13, 2, 59, 59, tzinfo=dt.timezone.utc)
    assert not c.vencido(dt.datetime(2026, 9, 13, 2, 0, tzinfo=dt.timezone.utc))
    assert c.vencido(dt.datetime(2026, 9, 13, 3, 0, tzinfo=dt.timezone.utc))


@pytest.mark.django_db
def test_sin_fecha_no_vence_nunca():
    c = cupon()
    assert c.vence_at is None
    assert not c.vencido(dt.datetime(2099, 1, 1, tzinfo=dt.timezone.utc))


@pytest.mark.django_db
def test_el_mismo_external_id_no_registra_dos_usos():
    c = cupon()
    acc = Account.objects.create(email="u@x.com")
    CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                            descuento_centavos=870, monto_pagado_centavos=2030,
                            external_id="stripe:session:cs_1")
    with pytest.raises(IntegrityError), transaction.atomic():
        CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                                descuento_centavos=870, monto_pagado_centavos=2030,
                                external_id="stripe:session:cs_1")


@pytest.mark.django_db
def test_borrar_la_cuenta_deja_el_uso_sin_cuenta_y_no_devuelve_el_lugar():
    c = cupon(usos_maximos=1)
    acc = Account.objects.create(email="u@x.com")
    CuponUso.objects.create(cupon=c, account=acc, codigo_producto="informe_natal",
                            descuento_centavos=870, monto_pagado_centavos=2030,
                            external_id="stripe:session:cs_2")

    acc.delete()

    uso = CuponUso.objects.get()
    assert uso.account is None
    assert c.usos_confirmados() == 1


@pytest.mark.django_db
def test_un_cupon_con_usos_no_se_puede_borrar():
    c = cupon()
    CuponUso.objects.create(cupon=c, codigo_producto="informe_natal", descuento_centavos=870,
                            monto_pagado_centavos=2030, external_id="stripe:session:cs_3")
    with pytest.raises(IntegrityError), transaction.atomic():
        c.delete()


@pytest.mark.django_db
def test_un_checkout_sin_cupon_no_lleva_descuento():
    """El webhook lee el descuento congelado de la fila: sin cupón tiene que
    ser 0, no NULL, para que `monto == precio - descuento` cierre igual."""
    from api.models import PasarelaCheckout

    fila = PasarelaCheckout.objects.create(checkout_id="cs_sin", codigo_producto="informe_natal")
    assert fila.cupon is None
    assert fila.descuento_centavos == 0
