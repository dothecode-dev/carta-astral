import datetime
from dataclasses import dataclass

from django.db import transaction

from core.ephemeris import build_chart
from core.models import BirthInput, ChartData
from core.timeconv import resolve_tz

from api.models import BirthData, Chart
from api.serializers import serialize_chart_data
from api.versioning import engine_version


@dataclass(frozen=True)
class CartaCalculada:
    """Una carta calculada y todavía no guardada.

    Existe porque hay dos consumidores del mismo cálculo: quien tiene cuenta y
    guarda su carta, y el visitante que todavía no tiene y sólo la mira
    (`/api/charts/preview/`, 04-09-2026). Antes el cálculo y el `INSERT` eran
    una sola función, así que ver una carta obligaba a crear una cuenta —y a
    guardar la fecha, la hora y el lugar de nacimiento de alguien que no había
    aceptado nada—.
    """

    birth_input: BirthInput
    data: ChartData
    tz_name: str
    datetime_utc: datetime.datetime | None
    place_label: str


def calcular(payload: dict) -> CartaCalculada:
    """Efemérides puras: no toca la base ni necesita cuenta.

    Levanta `KeyError` si falta un campo obligatorio, `ValueError` si alguno no
    parsea y `CoreError` si el cálculo no se puede hacer; quien llama los
    traduce a 400.
    """
    date = datetime.date.fromisoformat(payload["date"])
    time_known = bool(payload.get("time_known", payload.get("time") is not None))
    time = (
        datetime.time.fromisoformat(payload["time"])
        if time_known and payload.get("time")
        else None
    )
    lat = float(payload["lat"])
    lng = float(payload["lng"])

    birth_input = BirthInput(
        name=payload.get("name"), date=date, time=time, time_known=time_known,
        lat=lat, lng=lng,
        house_system=payload.get("house_system", "Placidus"),
        zodiac=payload.get("zodiac", "Tropical"),
    )
    chart_data = build_chart(birth_input)

    return CartaCalculada(
        birth_input=birth_input,
        data=chart_data,
        tz_name=resolve_tz(lat, lng),
        datetime_utc=(
            datetime.datetime.fromisoformat(chart_data.utc_iso)
            if chart_data.time_known
            else None
        ),
        place_label=str(payload.get("place_label", ""))[:200],
    )


def create_chart(payload: dict, account) -> Chart:
    """Calcula y guarda. El cálculo es el mismo de `calcular`, a propósito: si
    se bifurcan, la carta que vio el visitante deja de ser la que recibe."""
    carta_calc = calcular(payload)
    bi = carta_calc.birth_input

    with transaction.atomic():
        birth_data = BirthData.objects.create(
            name=bi.name, date=bi.date, time=bi.time, time_known=carta_calc.data.time_known,
            lat=bi.lat, lng=bi.lng, tz_name=carta_calc.tz_name,
            datetime_utc=carta_calc.datetime_utc, place_label=carta_calc.place_label,
        )
        carta = Chart.objects.create(
            birth_data=birth_data,
            house_system=carta_calc.data.house_system,
            zodiac=carta_calc.data.zodiac,
            data=serialize_chart_data(carta_calc.data),
            engine_version=engine_version(),
            account=account,
        )
        # El sujeto natal nace con la carta: es de él que va a colgar su informe.
        from api.sujetos import sujeto_natal

        sujeto_natal(carta)
        return carta
