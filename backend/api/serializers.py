import dataclasses

from core.models import ChartData


def serialize_chart_data(cd: ChartData) -> dict:
    d = dataclasses.asdict(cd)
    # El núcleo emite un mediodía-UTC artificial cuando la hora es desconocida;
    # no lo exponemos como si fuera un instante real.
    if not cd.time_known:
        d["utc_iso"] = None
    return d
