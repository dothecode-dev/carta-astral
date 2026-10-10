"""CONTRAER (parte 2 de Vínculo, deploy 2): nada en `api/` LEE la carta de un
informe, de un consumo o de un checkout (RF8). Desde el deploy 3 tampoco la
ESCRIBE: la columna sale del estado de Django y la borra el primer deploy de la
parte 3, así que una escritura que sobreviva rompería ahí."""

import pathlib
import re

API = pathlib.Path(__file__).resolve().parents[2] / "api"
PROHIBIDO = re.compile(
    r"\b(interpretacion|interpretation|origen|fila|i)\.chart(_id)?\b"
    r"|\bchart\.interpretations\b|\bobj\.interpretations\b"
    r"|(Interpretation|Movimiento|PasarelaCheckout)\.objects\.filter\([^)]*\bchart="
    r"|select_related\([^)]*\"chart\""
    r"|_lock_key_viejo|adoptar_huerfanas"
)


def test_ningun_modulo_lee_la_carta_de_un_informe_o_un_checkout():
    culpables = [
        f"{p.relative_to(API.parent)}:{n}: {linea.strip()}"
        for p in API.rglob("*.py") if "migrations" not in p.parts
        for n, linea in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if PROHIBIDO.search(linea)
    ]
    assert culpables == []


# `"chart": …natal_de` y no `"chart"` a secas: esa clave también es una
# propiedad de los eventos de analítica (un uuid) y el scope de un throttle.
# Los campos `"chart"` de los admins de estos modelos los atrapa
# `test_ningun_admin_muestra_la_carta`.
ESCRITURA = re.compile(
    r"(Interpretation|Movimiento|PasarelaCheckout)\.objects\.\w+\([^)]*\bchart="
    r"|\.update\([^)]*\bchart=|\bfila\.chart\s*=|\"chart\":\s*[\w.]*natal_de"
    # Por un helper (`_movimiento_idempotente(..., chart=…)`): la forma de arriba
    # sólo ve el `create` directo, y así se le escapó la devolución.
    r"|\bchart=[\w.]*natal_de",
    re.S,
)


def test_ningun_modulo_escribe_la_carta_de_un_informe_o_un_checkout():
    culpables = [
        str(p.relative_to(API.parent))
        for p in API.rglob("*.py") if "migrations" not in p.parts
        and ESCRITURA.search(p.read_text(encoding="utf-8"))
    ]
    assert culpables == []


def test_ningun_admin_muestra_la_carta():
    from django.contrib import admin

    from api.models import Interpretation, Movimiento, PasarelaCheckout

    for modelo in (Interpretation, Movimiento, PasarelaCheckout):
        ma = admin.site._registry[modelo]
        campos = (*ma.list_display, *(ma.fields or ()), *ma.readonly_fields, *ma.search_fields)
        assert not [c for c in campos if c == "chart" or c.startswith("chart__")], modelo.__name__
