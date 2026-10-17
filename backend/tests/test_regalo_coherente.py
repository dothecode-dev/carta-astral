import re
from pathlib import Path

from django.conf import settings

RAIZ = Path(__file__).resolve().parent.parent.parent


def test_la_web_promete_las_mismas_lecturas_que_regala_el_backend():
    """La web espeja en `regalo.ts` cuántas lecturas regala una cuenta nueva. Si
    alguien cambia el regalo efectivo y no toca la web, la pantalla miente.

    El regalo efectivo es `INSTALL_FREE_CREDITS` sólo con
    `LECTURA_BREVE_GRATIS_ENABLED` prendido; con el flag en su default (apagado)
    es 0. Prender el flag exige cambiar `regalo.ts` y los textos de la web que
    hoy no prometen ninguna lectura: es un deploy de la web, no sólo de una
    variable de entorno."""
    fuente = (RAIZ / "web" / "lib" / "regalo.ts").read_text(encoding="utf-8")
    match = re.search(r"LECTURAS_DE_REGALO\s*=\s*(\d+)", fuente)
    assert match, "web/lib/regalo.ts debe exportar LECTURAS_DE_REGALO"
    regalo_efectivo = (
        settings.INSTALL_FREE_CREDITS if settings.LECTURA_BREVE_GRATIS_ENABLED else 0
    )
    assert int(match.group(1)) == regalo_efectivo


def test_el_regalo_no_se_lee_del_entorno():
    """El test de arriba compara contra el valor del CÓDIGO. Si el regalo se
    pudiera pisar con una variable de Coolify, ese test seguiría verde con la
    web prometiendo otro número: la cantidad vive sólo acá, y cambiarla es un
    deploy, que es lo que de todos modos hace falta para cambiar los textos."""
    fuente = (RAIZ / "backend" / "config" / "settings.py").read_text(encoding="utf-8")
    linea = next(
        renglon for renglon in fuente.splitlines() if renglon.startswith("INSTALL_FREE_CREDITS")
    )
    assert "environ" not in linea, linea
