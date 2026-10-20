"""Cada módulo del cobro se puede importar PRIMERO, en un intérprete limpio.

Dentro de pytest el orden de import lo fija la colección y un ciclo queda
tapado: el primer test ya importó todo. En producción el que importa primero
es el comando del cron (`vencer_checkouts` → `mercadopago_cron`) o el webhook,
y ahí un ciclo es un `ImportError` en cada corrida. Pasó: `cobro` →
`compra_anonima` → `apertura` → `pasarelas` cerraba un ciclo que rompía
importar primero cualquier submódulo de Mercado Pago.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]

MODULOS = [
    "api.cobro",
    "api.pasarelas.mercadopago",
    "api.pasarelas.mercadopago_pagos",
    "api.pasarelas.mercadopago_disputas",
    "api.pasarelas.mercadopago_cron",
]


@pytest.mark.parametrize("modulo", MODULOS)
def test_se_importa_primero_en_un_proceso_limpio(modulo):
    codigo = (
        "import django; django.setup(); "
        f"import importlib; importlib.import_module({modulo!r})"
    )
    entorno = {**os.environ, "DJANGO_SETTINGS_MODULE": "config.settings", "DEBUG": "1"}
    r = subprocess.run(
        [sys.executable, "-c", codigo], cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=120,
    )
    assert r.returncode == 0, r.stderr
