"""El entrypoint corre los chequeos de arranque que avisan por Telegram
(`AVISAR_CHECKS=1`). Un tag que falte ahí es un chequeo que nunca avisa."""

import re
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parent.parent / "entrypoint.sh"


def test_el_chequeo_de_arranque_corre_stripe_y_mercadopago():
    lineas = [ln for ln in ENTRYPOINT.read_text().splitlines() if ln.startswith("AVISAR_CHECKS=1 ")]
    assert len(lineas) == 1
    tags = set(re.findall(r"--tag (\S+)", lineas[0]))
    assert tags == {"stripe", "mercadopago"}
