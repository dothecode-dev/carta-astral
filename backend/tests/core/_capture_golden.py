import dataclasses
import datetime
import json
import pathlib

from core.models import BirthInput
from core.ephemeris import build_chart

CASES = {
    "exact_olivos_1989": BirthInput(
        name="Olivos",
        date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45),
        time_known=True,
        lat=-34.5,
        lng=-58.4,
    ),
    "exact_london_1990": BirthInput(
        name="London",
        date=datetime.date(1990, 1, 1),
        time=datetime.time(0, 0),
        time_known=True,
        lat=51.5,
        lng=-0.12,
    ),
    "degraded_polar_1989": BirthInput(
        name="Polar",
        date=datetime.date(1989, 7, 14),
        time=datetime.time(12, 0),
        time_known=True,
        lat=78.0,
        lng=15.0,
    ),
    "dst_useastern_2021": BirthInput(
        name="DST",
        date=datetime.date(2021, 11, 7),
        time=datetime.time(1, 30),
        time_known=True,
        lat=40.7,
        lng=-74.0,
    ),
    "notime_olivos_1989": BirthInput(
        name="NoTime",
        date=datetime.date(1989, 7, 14),
        time=None,
        time_known=False,
        lat=-34.5,
        lng=-58.4,
    ),
}


def capture() -> None:
    out = pathlib.Path(__file__).parent / "golden"
    out.mkdir(exist_ok=True)
    for key, bi in CASES.items():
        cd = build_chart(bi)
        (out / f"{key}.json").write_text(
            json.dumps(dataclasses.asdict(cd), indent=2, default=str)
        )
    print("capturados:", list(CASES))


if __name__ == "__main__":
    capture()
