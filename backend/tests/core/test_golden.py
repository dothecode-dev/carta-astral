import dataclasses
import json
import pathlib

import pytest

from core.ephemeris import build_chart
from tests.core._capture_golden import CASES

GOLDEN = pathlib.Path(__file__).parent / "golden"

# Los golden se capturaron en macOS/ARM y el CI corre en Linux/x86. La libm de
# cada plataforma da resultados que difieren en el orden de 1e-8 grados, así que
# comparar por igualdad exacta hacía fallar la suite entera en CI por unas
# diezmilésimas de segundo de arco: ruido de punto flotante, no astronomía.
#
# La tolerancia es deliberadamente chica: 1e-6 grados son 0,0036 segundos de
# arco. Cualquier regresión real de cálculo (un signo cambiado, otro sistema de
# casas, un offset horario mal aplicado) mueve las posiciones muchísimo más y
# sigue rompiendo el test.
TOLERANCIA_GRADOS = 1e-6


def _comparar(actual, esperado, ruta=""):
    """Igualdad estricta en todo, salvo en los float."""
    assert type(actual) is type(esperado), f"cambió el tipo en {ruta}"

    if isinstance(esperado, dict):
        assert set(actual) == set(esperado), f"cambiaron las claves en {ruta}"
        for k in esperado:
            _comparar(actual[k], esperado[k], f"{ruta}.{k}")
    elif isinstance(esperado, list):
        assert len(actual) == len(esperado), f"cambió la cantidad de elementos en {ruta}"
        for i, (a, e) in enumerate(zip(actual, esperado)):
            _comparar(a, e, f"{ruta}[{i}]")
    elif isinstance(esperado, float):
        assert actual == pytest.approx(esperado, abs=TOLERANCIA_GRADOS), (
            f"{ruta}: {actual} != {esperado}"
        )
    else:
        # Strings, bools, None y enteros van por igualdad estricta: un flag que
        # cambia de valor, o una casa que pasa de None a un número, SON
        # regresiones y tienen que romper.
        assert actual == esperado, f"{ruta}: {actual!r} != {esperado!r}"


@pytest.mark.parametrize("key", list(CASES))
def test_golden_matches(key: str) -> None:
    expected = json.loads((GOLDEN / f"{key}.json").read_text())
    actual = json.loads(json.dumps(dataclasses.asdict(build_chart(CASES[key])), default=str))
    _comparar(actual, expected, key)
