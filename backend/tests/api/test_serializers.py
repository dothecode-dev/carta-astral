import datetime
from core.models import BirthInput
from core.ephemeris import build_chart
from api.serializers import serialize_chart_data


def _olivos(time_known=True):
    return BirthInput(
        name="T", date=datetime.date(1989, 7, 14),
        time=datetime.time(23, 45) if time_known else None,
        time_known=time_known, lat=-34.5, lng=-58.4,
    )


def test_serialize_includes_placements_and_utc_when_time_known():
    d = serialize_chart_data(build_chart(_olivos(True)))
    assert isinstance(d["placements"], list) and len(d["placements"]) > 0
    assert d["utc_iso"] is not None


def test_serialize_nulls_utc_when_time_unknown():
    d = serialize_chart_data(build_chart(_olivos(False)))
    assert d["utc_iso"] is None
    assert d["houses"] is None
