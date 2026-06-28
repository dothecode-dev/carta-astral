import datetime

from core.ephemeris import build_chart
from core.models import BirthInput
from core.timeconv import resolve_tz

from api.models import BirthData, Chart
from api.serializers import serialize_chart_data
from api.versioning import engine_version


def create_chart(payload: dict) -> Chart:
    date = datetime.date.fromisoformat(payload["date"])
    time_known = bool(payload.get("time_known", payload.get("time") is not None))
    time = (
        datetime.time.fromisoformat(payload["time"])
        if time_known and payload.get("time")
        else None
    )
    lat = float(payload["lat"])
    lng = float(payload["lng"])
    house_system = payload.get("house_system", "Placidus")
    zodiac = payload.get("zodiac", "Tropical")

    birth_input = BirthInput(
        name=payload.get("name"), date=date, time=time, time_known=time_known,
        lat=lat, lng=lng, house_system=house_system, zodiac=zodiac,
    )
    chart_data = build_chart(birth_input)
    tz_name = resolve_tz(lat, lng)

    datetime_utc = None
    if time_known:
        datetime_utc = datetime.datetime.fromisoformat(chart_data.utc_iso)

    birth_data = BirthData.objects.create(
        name=payload.get("name"), date=date, time=time, time_known=time_known,
        lat=lat, lng=lng, tz_name=tz_name, datetime_utc=datetime_utc,
    )
    return Chart.objects.create(
        birth_data=birth_data, house_system=chart_data.house_system, zodiac=zodiac,
        data=serialize_chart_data(chart_data), engine_version=engine_version(),
    )
