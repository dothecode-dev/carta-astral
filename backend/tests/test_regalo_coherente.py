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
