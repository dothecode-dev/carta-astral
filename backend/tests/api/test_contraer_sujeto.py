"""CONTRAER (parte 2 de Vínculo, deploy 2): nada en `api/` LEE la carta de un
informe, de un consumo o de un checkout (RF8). Escribir `chart=` todavía se
permite: es lo que deja volver al deploy 1. El deploy 3 endurece esta guardia."""

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
