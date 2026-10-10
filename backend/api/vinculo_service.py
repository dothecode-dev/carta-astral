"""Crear un vínculo (parte 3 de la spec de Vínculo).

Las dos personas se guardan como COPIAS (`Chart.en_lista=False`, RF15): una
foto de los datos con los que se calculó, que no cambia si después se corrige
o se borra la carta original, y que ningún camino de carta alcanza (RF12).
Sin nombre: lo único que identifica a cada persona es su alias, que vive en
`sujeto.parametros` y NO entra al prompt (RF22)."""

import uuid
from dataclasses import asdict

from django.db import transaction

from api.chart_service import calcular
from api.models import BirthData, Chart, Sujeto, SujetoCarta
from api.serializers import serialize_chart_data
from api.vinculo_tipos import VinculoInvalido, validar
from api.versioning import engine_version
from core.exceptions import CoreError
from core.sinastria import aspectos_cruzados, superposicion

ALIAS_MAX = 40
_CAMPOS = ("date", "time", "time_known", "lat", "lng", "place_label")


def _payload(persona: dict, account):
    if "carta" in persona:
        try:
            carta_uuid = uuid.UUID(str(persona["carta"]))
        except ValueError:
            # «abc», "" o un objeto: un pedido mal armado (400), no un 500.
            raise VinculoInvalido("datos_invalidos") from None
        original = Chart.objects.get(uuid=carta_uuid, account=account)
        bd = original.birth_data
        return {
            "date": bd.date.isoformat(),
            "time": bd.time.isoformat(timespec="minutes") if bd.time else None,
            "time_known": bd.time_known, "lat": bd.lat, "lng": bd.lng,
            "house_system": original.house_system, "zodiac": original.zodiac,
            "place_label": bd.place_label,
        }
    # Sin `name` a propósito: el tercero no se guarda con nombre.
    return {k: persona[k] for k in _CAMPOS if k in persona}


def _alias(persona: dict) -> str:
    valor = persona.get("alias", "")
    if not isinstance(valor, str) or len(valor.strip()) > ALIAS_MAX:
        raise VinculoInvalido("alias_invalido")
    return valor.strip()


def _copia(calc, account) -> Chart:
    bi = calc.birth_input
    bd = BirthData.objects.create(
        name=None, date=bi.date, time=bi.time, time_known=calc.data.time_known,
        lat=bi.lat, lng=bi.lng, tz_name=calc.tz_name,
        datetime_utc=calc.datetime_utc, place_label=calc.place_label,
    )
    return Chart.todas.create(
        birth_data=bd, house_system=calc.data.house_system, zodiac=calc.data.zodiac,
        data=serialize_chart_data(calc.data), engine_version=engine_version(),
        account=account, en_lista=False,
    )


def crear_vinculo(account, tipo: str, personas: list[dict]) -> Sujeto:
    if (not isinstance(personas, list) or len(personas) != 2
            or not all(isinstance(p, dict) for p in personas)):
        raise VinculoInvalido("personas")
    rol_a, rol_b = validar(tipo, personas[0].get("rol", ""), personas[1].get("rol", ""))
    alias_ = [_alias(p) for p in personas]
    try:
        calc_a, calc_b = (calcular(_payload(p, account)) for p in personas)
    except Chart.DoesNotExist:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, CoreError):
        raise VinculoInvalido("datos_invalidos") from None
    if calc_a.birth_input == calc_b.birth_input:
        raise VinculoInvalido("misma_persona")

    with transaction.atomic():
        a, b = _copia(calc_a, account), _copia(calc_b, account)
        sujeto = Sujeto.objects.create(
            producto=Sujeto.VINCULO, account=account, engine_version=engine_version(),
            parametros={"tipo": tipo, "roles": [rol_a, rol_b], "alias": alias_},
            data={
                "aspectos": [asdict(x) for x in aspectos_cruzados(calc_a.data, calc_b.data)],
                "a_en_b": superposicion(calc_a.data, calc_b.data),
                "b_en_a": superposicion(calc_b.data, calc_a.data),
            },
        )
        SujetoCarta.objects.create(sujeto=sujeto, carta=a, orden=0, rol=rol_a)
        SujetoCarta.objects.create(sujeto=sujeto, carta=b, orden=1, rol=rol_b)
    return sujeto


def cartas(sujeto: Sujeto) -> tuple[Chart, Chart]:
    a, b = (sc.carta for sc in sujeto.cartas.select_related("carta__birth_data"))
    return a, b


def alias(sujeto: Sujeto) -> tuple[str, str]:
    a, b = sujeto.parametros.get("alias", ["", ""])
    return a, b


def datos_prompt(sujeto: Sujeto) -> dict:
    """Lo que ve el modelo. Sin alias (RF22); las cartas en orden y con su rol
    (RF14)."""
    a, b = cartas(sujeto)
    rol_a, rol_b = sujeto.parametros["roles"]
    return {
        "tipo": sujeto.parametros["tipo"],
        "persona_a": {"rol": rol_a, "carta": a.data},
        "persona_b": {"rol": rol_b, "carta": b.data},
        "aspectos_cruzados": sujeto.data["aspectos"],
        "planetas_de_a_en_casas_de_b": sujeto.data["a_en_b"],
        "planetas_de_b_en_casas_de_a": sujeto.data["b_en_a"],
    }
