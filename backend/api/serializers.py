import dataclasses

from core.models import ChartData


def serialize_chart_data(cd: ChartData) -> dict:
    d = dataclasses.asdict(cd)
    # Lista y no tupla: es lo que devuelve el JSON guardado, y una carta
    # recién calculada tiene que ser igual a la misma carta leída de la base.
    d["flags"]["moon_sign_options"] = list(cd.flags.moon_sign_options)
    # El núcleo calcula al mediodía local cuando la hora es desconocida; ese
    # instante es artificial y no lo exponemos como si fuera real.
    if not cd.time_known:
        d["utc_iso"] = None
    return d
