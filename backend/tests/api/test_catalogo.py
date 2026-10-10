import pytest

from api.catalogo import (
    ACCESO, CATALOGO, CONSUMIBLE, Producto, a_la_venta, producto, productos_con_capacidad,
)

# Este archivo fija los precios de verdad: corre sin el precio de prueba de
# `tests/api/conftest.py`.
pytestmark = pytest.mark.catalogo_real


def test_catalogo_tiene_exactamente_los_productos_de_esta_iteracion():
    assert set(CATALOGO) == {
        "lectura_breve", "informe_natal", "pack_3_natal", "pack_5_natal", "informe_vinculo",
    }


@pytest.mark.parametrize(
    "codigo,precio,otorga,capacidades",
    [
        ("lectura_breve", 0, (("lectura_breve", 1),), ("leer_breve",)),
        ("informe_natal", 500, (("informe_natal", 1),), ("leer_informe",)),
        ("pack_3_natal", 7900, (("informe_natal", 3),), ("leer_informe",)),
        ("pack_5_natal", 12500, (("informe_natal", 5),), ("leer_informe",)),
    ],
)
def test_precios_y_otorgamientos_exactos(codigo, precio, otorga, capacidades):
    p = producto(codigo)
    assert (p.precio_centavos, p.otorga, p.capacidades) == (precio, otorga, capacidades)
    assert p.naturaleza == CONSUMIBLE


def test_todo_producto_declara_capacidades_no_vacias_y_naturaleza_valida():
    for p in CATALOGO.values():
        assert p.capacidades, f"{p.codigo} no declara capacidades"
        assert p.naturaleza in (CONSUMIBLE, ACCESO)


def test_un_producto_de_acceso_declara_duracion():
    # El tipo existe aunque el catálogo no tenga ninguno hoy: agregarlo después
    # obligaría a migrar compras con plata real adentro (spec RF3).
    plan = Producto(
        codigo="plan_demo", precio_centavos=999, naturaleza=ACCESO,
        capacidades=("leer_informe",), otorga=(("plan_demo", 1),), duracion_dias=30,
    )
    assert plan.duracion_dias == 30


def test_producto_de_acceso_sin_duracion_es_invalido():
    with pytest.raises(ValueError, match="duracion_dias"):
        Producto(
            codigo="malo", precio_centavos=1, naturaleza=ACCESO,
            capacidades=("x",), otorga=(("malo", 1),), duracion_dias=None,
        )


def test_productos_con_capacidad_encuentra_todos_los_que_dan_leer_informe():
    codigos = {p.codigo for p in productos_con_capacidad("leer_informe")}
    assert codigos == {"informe_natal", "pack_3_natal", "pack_5_natal"}


def test_producto_desconocido_falla_con_su_codigo_en_el_mensaje():
    with pytest.raises(KeyError, match="pack_100"):
        producto("pack_100")


def test_ningun_producto_pago_otorga_lectura_breve():
    """Blinda la premisa del cálculo anti-abuso de `api.deletion.free_consumidas`.

    Ese cálculo es `INSTALL_FREE_CREDITS - suma de los movimientos de
    lectura_breve`, y sólo es correcto porque `lectura_breve` es exclusivamente
    de regalo. Si mañana un producto pago lo otorgara, las unidades COMPRADAS
    inflarían el restante, el tombstone quedaría por DEBAJO de lo realmente
    consumido y borrar la cuenta para volver a entrar regalaría lecturas
    gratis de nuevo. Que el catálogo cambie está bien; que lo haga en silencio
    y abra ese agujero, no: si este test se pone rojo, hay que rehacer
    `free_consumidas` (por ejemplo, filtrando por `origen="regalo"`) antes de
    tocar el catálogo.
    """
    pagos = [p.codigo for p in CATALOGO.values()
             if p.precio_centavos > 0 and p.otorga[0] == "lectura_breve"]
    assert pagos == []


def test_ningun_pack_sale_mas_caro_que_comprar_de_a_uno():
    """Un pack que no descuenta no es un pack: es un recargo por comprar de a
    muchos.

    Pasó de verdad y estuvo en el catálogo hasta el 02-09-2026: el pack de 5
    valía US$ 149,90 cuando cinco informes sueltos costaban US$ 145,00 — casi
    US$ 5 de castigo por llevar más. Nadie lo elige salvo por error, y quien lo
    nota siente que se lo quisieron pasar.

    Sólo lo que está a la venta: los packs retirados el 04-10-2026 conservan
    su precio de entonces (US$ 79 y 125) contra un informe que hoy vale 5.
    """
    for prod in a_la_venta():
        for codigo, cantidad in prod.otorga:
            if cantidad <= 1 or codigo not in CATALOGO:
                continue
            suelto = CATALOGO[codigo].precio_centavos
            if suelto == 0:
                continue
            sumados = suelto * cantidad
            assert prod.precio_centavos < sumados, (
                f"{prod.codigo} cuesta {prod.precio_centavos} y las {cantidad} "
                f"unidades sueltas de {codigo} cuestan {sumados}: "
                "el pack sale más caro que comprar de a uno"
            )



def test_lo_unico_a_la_venta_es_el_informe_natal():
    assert [p.codigo for p in a_la_venta()] == ["informe_natal"]
