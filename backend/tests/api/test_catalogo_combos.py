"""Un producto puede otorgar más de una cosa.

`Producto.otorga` era una sola tupla `(código, cantidad)`: alcanzaba para un
pack —cinco unidades del MISMO producto— pero no para un combo, que da dos
productos distintos. Agregar "combo carta + horóscopo" al catálogo tenía que
ser una línea y no lo era: había que tocar `otorgar`, `revocar` y las tres
consultas que preguntan qué producto otorga qué.
"""

import pytest

from api.canje import aplicar_compra, revocar
from api.catalogo import CATALOGO, Producto
from api.models import Derecho

pytestmark = pytest.mark.django_db


@pytest.fixture
def combo(monkeypatch):
    p = Producto(
        "combo_carta_horoscopo", 3900, "consumible",
        ("leer_informe", "leer_horoscopo"),
        (("informe_natal", 1), ("horoscopo", 1)),
    )
    monkeypatch.setitem(CATALOGO, p.codigo, p)
    return p


def _derechos(cuenta) -> dict:
    return dict(
        Derecho.objects.filter(account=cuenta).values_list("codigo_producto", "cantidad_restante")
    )


def test_un_combo_otorga_los_dos_productos(make_account, combo):
    cuenta = make_account()

    aplicar_compra(cuenta, "combo_carta_horoscopo", 3900, external_id="stripe:order:c1")

    tiene = _derechos(cuenta)
    assert tiene.get("informe_natal") == 1
    assert tiene.get("horoscopo") == 1


def test_reembolsar_un_combo_baja_los_dos(make_account, combo):
    """Si el reembolso sólo bajara uno, la mitad del combo queda regalada."""
    cuenta = make_account()
    aplicar_compra(cuenta, "combo_carta_horoscopo", 3900, external_id="stripe:order:c2")

    revocar(cuenta, "combo_carta_horoscopo", 1, external_id="stripe:refund:c2")

    tiene = _derechos(cuenta)
    assert tiene.get("informe_natal") == 0
    assert tiene.get("horoscopo") == 0
