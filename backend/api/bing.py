"""Lo que Bing dice del sitio, para el informe diario.

Es la misma pregunta que `informe_actividad.busquedas` le hace a Search Console
—impresiones, clics, qué consultas te muestran— contra la API de Bing Webmaster
Tools. Importa porque Bing es el índice que usa ChatGPT para buscar: lo que
Bing sabe del sitio es lo que una IA puede citar.

**La clave viaja en la URL** (`?apikey=...`), que es como la API de Bing la
pide. Eso tiene una consecuencia: `httpx` pone la URL completa en el mensaje de
sus excepciones, así que cualquier error sin tratar escribiría la clave en un
log o, peor, en el mail del informe. Por eso acá NINGUNA excepción de red sale
tal cual: se convierte en `FuenteCaida` con un mensaje sin la URL.

Bing publica con retraso y al principio no tiene casi nada: un informe en cero
los primeros días es lo esperable, no un fallo.
"""

import datetime
import logging
import re

import httpx
from django.conf import settings

from api.informe_actividad import _TIMEOUT, FuenteCaida

logger = logging.getLogger(__name__)

_BASE = "https://ssl.bing.com/webmaster/api.svc/json"
_MS = re.compile(r"/Date\((-?\d+)")


def _fecha(valor: str) -> datetime.date:
    """El formato de fecha de la API: `/Date(1760054400000)/` o con zona."""
    m = _MS.search(valor)
    if not m:
        raise ValueError("fecha ilegible")
    ms = int(m.group(1))
    return datetime.datetime.fromtimestamp(ms / 1000, tz=datetime.timezone.utc).date()


def _pedir(metodo: str) -> list[dict]:
    """Un método de la API, o `FuenteCaida` sin la clave en el mensaje."""
    try:
        respuesta = httpx.get(
            f"{_BASE}/{metodo}",
            params={"siteUrl": settings.BING_SITE_URL, "apikey": settings.BING_WEBMASTER_API_KEY},
            timeout=_TIMEOUT,
        )
        respuesta.raise_for_status()
        return respuesta.json().get("d") or []
    except httpx.HTTPStatusError as exc:
        codigo = exc.response.status_code if exc.response is not None else "?"
        raise FuenteCaida(f"Bing respondió {codigo} a {metodo}") from None
    except (httpx.HTTPError, ValueError) as exc:
        # `from None`: el `__cause__` de httpx trae la URL con la clave.
        raise FuenteCaida(f"Bing no contestó a {metodo} ({type(exc).__name__})") from None


def busquedas(dias: int = 7, hoy: datetime.date | None = None) -> dict:
    """Clics, impresiones, consultas y páginas de los últimos `dias`, contra los
    `dias` anteriores. La ventana termina ayer: hoy está incompleto."""
    if not settings.BING_WEBMASTER_API_KEY:
        raise FuenteCaida("Bing sin clave: falta BING_WEBMASTER_API_KEY")

    hoy = hoy or datetime.date.today()
    hasta = hoy - datetime.timedelta(days=1)
    desde = hasta - datetime.timedelta(days=dias - 1)
    desde_previo = desde - datetime.timedelta(days=dias)

    por_dia = [
        (_fecha(f["Date"]), f.get("Clicks", 0), f.get("Impressions", 0))
        for f in _pedir("GetRankAndTrafficStats")
    ]
    actual = [(d, c, i) for d, c, i in por_dia if desde <= d <= hasta]
    previo = [(d, c, i) for d, c, i in por_dia if desde_previo <= d < desde]

    return {
        "ventana": f"{desde.isoformat()} a {hasta.isoformat()}",
        "clics": sum(c for _, c, _ in actual),
        "impresiones": sum(i for _, _, i in actual),
        "previo": {
            "clics": sum(c for _, c, _ in previo),
            "impresiones": sum(i for _, _, i in previo),
        },
        "dias_con_actividad": len({d for d, c, i in actual if c or i}),
        "consultas": [
            {
                "consulta": f["Query"],
                "impresiones": f.get("Impressions", 0),
                "clics": f.get("Clicks", 0),
                "posicion": float(f.get("AvgImpressionPosition", 0)),
            }
            # La API devuelve el histórico entero; el informe quiere las primeras.
            for f in _pedir("GetQueryStats")[:15]
        ],
        "paginas": [
            {
                "pagina": f["Query"],
                "impresiones": f.get("Impressions", 0),
                "clics": f.get("Clicks", 0),
            }
            for f in _pedir("GetPageStats")[:10]
        ],
    }
