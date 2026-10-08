import datetime
import math
from dataclasses import dataclass

from django.db import transaction

from core.ephemeris import HOUSE_SYSTEMS, ZODIACS, build_chart
from core.models import BirthInput, ChartData
from core.timeconv import resolve_tz
from interpret.trato import TRATOS

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


def mensaje_de_datos_invalidos(exc: Exception) -> str:
    """El texto del 400 cuando `calcular` rechaza el pedido.

    Un `KeyError` pelado se serializaba como su repr (`"'date'"`); acá dice
    qué campo falta. `ValueError` y `CoreError` ya traen un mensaje legible.
    """
    if isinstance(exc, KeyError) and exc.args:
        return f"falta el campo {exc.args[0]}"
    return str(exc)


MAX_TEXTO = 200  # `BirthData.name` y `place_label` son CharField(200)


def _texto(payload: dict, campo: str) -> str:
    """`name` y `place_label`: ausente o `null` es "", y lo largo se recorta
    a MAX_TEXTO como siempre (rechazarlo rompía cartas que antes andaban).
    Sólo otro tipo es inválido."""
    valor = payload.get(campo)
    if valor is None:
        return ""
    if not isinstance(valor, str):
        raise ValueError(f"{campo} inválido")
    return valor[:MAX_TEXTO]


def _coordenada(payload: dict, campo: str, limite: float) -> float:
    valor = payload[campo]
    # `bool` es subclase de `int`: `true` no es una latitud.
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"{campo} inválido")
    try:
        numero = float(valor)
    except OverflowError:  # un entero de 400 dígitos
        raise ValueError(f"{campo} inválido") from None
    if not math.isfinite(numero) or not -limite <= numero <= limite:
        raise ValueError(f"{campo} fuera de rango")
    return numero


def _de_lista(payload: dict, campo: str, validos: frozenset[str], default: str) -> str:
    valor = payload.get(campo, default)
    if not isinstance(valor, str) or valor not in validos:
        raise ValueError(f"{campo} inválido")
    return valor


def calcular(payload: dict) -> CartaCalculada:
    """Efemérides puras: no toca la base ni necesita cuenta.

    Valida el payload ENTERO antes de calcular (spec §11): tipos, rangos de
    lat/lng, `house_system`/`zodiac` de lo que `build_chart` soporta y tipo
    de los textos (los largos se recortan). Levanta `KeyError` si falta un
    campo obligatorio, `ValueError` si alguno es inválido y `CoreError` si el cálculo no se
    puede hacer; quien llama los traduce a 400. Un JSON con el tipo
    equivocado (`"date": 123`, `"house_system": ["x"]`, `"lat": 1e400`)
    llegaba hasta el motor como TypeError u OverflowError: un 500.
    """
    fecha = payload["date"]
    if not isinstance(fecha, str):
        raise ValueError("date inválida")
    date = datetime.date.fromisoformat(fecha)
    hora = payload.get("time")
    if hora is not None and not isinstance(hora, str):
        raise ValueError("time inválida")
    time_known = payload.get("time_known", hora is not None)
    if not isinstance(time_known, bool):
        raise ValueError("time_known inválido")
    time = datetime.time.fromisoformat(hora) if time_known and hora else None
    lat = _coordenada(payload, "lat", 90)
    lng = _coordenada(payload, "lng", 180)
    house_system = _de_lista(payload, "house_system", HOUSE_SYSTEMS, "Placidus")
    zodiac = _de_lista(payload, "zodiac", ZODIACS, "Tropical")
    name = _texto(payload, "name")
    place_label = _texto(payload, "place_label")

    birth_input = BirthInput(
        name=name, date=date, time=time, time_known=time_known,
        lat=lat, lng=lng, house_system=house_system, zodiac=zodiac,
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
        place_label=place_label,
    )


class TratoInvalido(ValueError):
    """El trato pedido no es uno de `TRATOS`. Es `ValueError` para que las vistas
    que ya mapean los datos inválidos a 400 lo traten igual."""


def validar_trato(valor) -> str:
    """El trato que se va a guardar. Ausente o `None` = «sin elegir» (`""`)."""
    if valor is None or valor == "":
        return ""
    if not isinstance(valor, str) or valor not in TRATOS:
        raise TratoInvalido("trato inválido")
    return valor


def cambiar_trato(chart: Chart, datos) -> None:
    """Cambia el trato de la carta con el cuerpo de un PATCH. Sólo afecta a los
    informes que se creen después: una `Interpretation` ya creada conserva el
    suyo (RF3).

    El cuerpo tiene que traer la clave `trato`: sin ella el PATCH no dice nada
    sobre el trato y no puede borrarlo. `null` y `""` sí son «sin elegir»."""
    if not hasattr(datos, "keys") or "trato" not in datos:
        raise TratoInvalido("trato inválido")
    trato = validar_trato(datos["trato"])
    birth = chart.birth_data
    birth.trato = trato
    birth.save(update_fields=["trato"])


def create_chart(payload: dict, account) -> Chart:
    """Calcula y guarda. El cálculo es el mismo de `calcular`, a propósito: si
    se bifurcan, la carta que vio el visitante deja de ser la que recibe."""
    trato = validar_trato(payload.get("trato"))
    carta_calc = calcular(payload)
    bi = carta_calc.birth_input

    with transaction.atomic():
        birth_data = BirthData.objects.create(
            name=bi.name, date=bi.date, time=bi.time, time_known=carta_calc.data.time_known,
            lat=bi.lat, lng=bi.lng, tz_name=carta_calc.tz_name,
            datetime_utc=carta_calc.datetime_utc, place_label=carta_calc.place_label,
            trato=trato,
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
