import dataclasses
import json
import pathlib

import pytest

from core.ephemeris import build_chart
from tests.core._capture_golden import CASES

GOLDEN = pathlib.Path(__file__).parent / "golden"


@pytest.mark.parametrize("key", list(CASES))
def test_golden_matches(key: str) -> None:
    expected = json.loads((GOLDEN / f"{key}.json").read_text())
    actual = json.loads(json.dumps(dataclasses.asdict(build_chart(CASES[key])), default=str))
    assert actual == expected
