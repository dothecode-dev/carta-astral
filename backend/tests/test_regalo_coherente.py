import re
from pathlib import Path

from django.conf import settings

RAIZ = Path(__file__).resolve().parent.parent.parent


def test_la_web_promete_las_mismas_lecturas_que_regala_el_backend():
    """El copy de /entrar promete un número de lecturas de regalo. Si alguien
    cambia INSTALL_FREE_CREDITS y no toca la web, la pantalla miente."""
    fuente = (RAIZ / "web" / "lib" / "regalo.ts").read_text(encoding="utf-8")
    match = re.search(r"LECTURAS_DE_REGALO\s*=\s*(\d+)", fuente)
    assert match, "web/lib/regalo.ts debe exportar LECTURAS_DE_REGALO"
    assert int(match.group(1)) == settings.INSTALL_FREE_CREDITS


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
