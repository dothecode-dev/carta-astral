"""Búsqueda de localidades (geocoding) aislada del framework.

Contrato del diseño: toda la lógica de geocode vive acá para poder cambiar de
proveedor (GeoNames) sin tocar views ni el resto. La view solo orquesta.
"""

from core.exceptions import GeocodeTimezoneError
from core.timeconv import resolve_tz

from api.models import GeoName
from api.text_norm import tokenize

MIN_QUERY_LEN = 2


def search(q: str, limit: int = 10) -> list[dict]:
    """Devuelve hasta `limit` candidatos que matchean TODOS los tokens de `q`.

    Los tokens completos (todos menos el último) matchean exacto; el último
    matchea por prefijo, para soportar autocomplete incremental. Rankea por
    población descendente. Lanza ValueError si la query es demasiado corta.
    """
    tokens = tokenize(q)
    if sum(len(t) for t in tokens) < MIN_QUERY_LEN:
        raise ValueError("query demasiado corto")

    *complete, last = tokens
    qs = GeoName.objects.all()
    for t in complete:
        # Cada filter sobre la relación reversa genera un join independiente:
        # el resultado son los GeoName que tienen TODOS los tokens (AND).
        qs = qs.filter(tokens__token=t)
    qs = qs.filter(tokens__token__startswith=last).distinct().order_by("-population")

    return [_candidate(g) for g in qs[:limit]]


def _candidate(g: GeoName) -> dict:
    parts = [g.name]
    if g.admin1:
        parts.append(g.admin1)
    parts.append(g.country_code)
    return {
        "place_query": ", ".join(parts),
        "name": g.name,
        "lat": g.lat,
        "lng": g.lng,
        "tz_name": _resolve_tz_name(g),
        "country_code": g.country_code,
        "admin1": g.admin1 or None,
        "population": g.population,
    }


def _resolve_tz_name(g: GeoName) -> str | None:
    """Deriva el tz desde lat/lng con la MISMA función que usa /api/charts/,
    para que lo mostrado coincida con lo calculado. Si el core no resuelve
    (ej. coords sin tz terrestre), cae al tz crudo de GeoNames, y si tampoco
    hay, a None."""
    try:
        return resolve_tz(g.lat, g.lng)
    except GeocodeTimezoneError:
        return g.tz_geonames or None
