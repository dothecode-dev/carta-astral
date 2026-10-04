import dataclasses

import pytest

from api import catalogo

#: El precio de lista con el que corren los tests de la mecánica del cobro
#: —webhook, cupones, reembolsos, compras—. Prueban cómo se valida y se
#: acredita un precio cualquiera, no cuánto vale hoy el informe: si leyeran el
#: precio real, cada cambio de precio rompería decenas de tests que no tienen
#: nada que ver. Cuánto vale de verdad lo fijan los tests marcados
#: `catalogo_real` (test_catalogo.py).
PRECIO_DE_PRUEBA = 2900


@pytest.fixture(autouse=True)
def _precio_de_prueba(request, monkeypatch):
    if request.node.get_closest_marker("catalogo_real"):
        return
    monkeypatch.setitem(
        catalogo.CATALOGO, "informe_natal",
        dataclasses.replace(catalogo.CATALOGO["informe_natal"], precio_centavos=PRECIO_DE_PRUEBA),
    )
