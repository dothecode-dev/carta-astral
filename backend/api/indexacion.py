"""Qué páginas del sitemap tiene Google indexadas, para el informe diario.

Pedir la indexación de una página nueva en Search Console no la indexa: la pone
en una cola. Saber si ya entró obligaba a entrar a mirar URL por URL. Esto lo
pregunta todos los días por la API de inspección y lo pone en el mail.

**Las URLs salen del sitemap, no de una lista a mano.** Así cada nota que se
publica entra sola en la revisión, y la que se borra sale sola. La cuota de la
API son 2.000 inspecciones por día y el sitemap tiene unas decenas de URLs.

Vive fuera de `informe_actividad.py`, que ya es largo, y reusa de ahí el token
de Google y la forma de avisar que una fuente no contestó.
"""

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor

import httpx
from django.conf import settings

from api.informe_actividad import _TIMEOUT, FuenteCaida, _token_google

logger = logging.getLogger(__name__)

_INSPECCION_URL = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

#: Inspecciones simultáneas. Cada una tarda ~7 s (medido el 05-10-2026 contra
#: Google: 36 URLs en fila fueron 4 min 28 s), y el cron le da 300 s al informe
#: entero. Con 8 a la vez queda en menos de un minuto, lejos de las 600 por
#: minuto que permite la cuota.
EN_PARALELO = 8

#: Un techo por si el sitemap crece: muy por debajo de la cuota diaria, y el
#: cron tiene 300 s para todo el informe.
MAX_URLS = 150


def _urls_del_sitemap() -> list[str]:
    respuesta = httpx.get(settings.SITEMAP_URL, timeout=_TIMEOUT)
    respuesta.raise_for_status()
    raiz = ET.fromstring(respuesta.text)
    urls = [loc.text.strip() for loc in raiz.iterfind("sm:url/sm:loc", _NS) if loc.text]
    # El sitemap no debería repetir, pero si lo hace no hay que gastar cuota.
    return list(dict.fromkeys(urls))[:MAX_URLS]


def estado_de_indexacion() -> dict:
    """Cuántas URLs del sitemap están indexadas y cuáles no, con el estado que
    da Google («URL is unknown to Google», «Discovered - currently not
    indexed»…), que dice en qué parte de la cola está cada una."""
    if not settings.GSC_SITE_URL:
        raise FuenteCaida("Search Console sin propiedad configurada")
    token = _token_google()
    try:
        urls = _urls_del_sitemap()
    except (httpx.HTTPError, ET.ParseError) as exc:
        raise FuenteCaida(f"no se pudo leer el sitemap: {type(exc).__name__}") from exc

    def inspeccionar(url: str) -> dict:
        try:
            respuesta = httpx.post(
                _INSPECCION_URL,
                headers={"Authorization": f"Bearer {token}"},
                json={"inspectionUrl": url, "siteUrl": settings.GSC_SITE_URL},
                timeout=_TIMEOUT,
            )
            respuesta.raise_for_status()
            resultado = respuesta.json()["inspectionResult"]["indexStatusResult"]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # Una URL que falla se cuenta como no confirmada y se sigue: el
            # resto del informe vale igual.
            logger.warning("no se pudo inspeccionar %s: %s", url, type(exc).__name__)
            return {"url": url, "indexada": False, "estado": "no se pudo inspeccionar"}
        return {
            "url": url,
            "indexada": resultado.get("verdict") == "PASS",
            "estado": resultado.get("coverageState", "sin estado"),
        }

    with ThreadPoolExecutor(max_workers=EN_PARALELO) as pool:
        resultados = list(pool.map(inspeccionar, urls))

    indexadas = sum(1 for r in resultados if r["indexada"])
    sin_indexar = [{"url": r["url"], "estado": r["estado"]} for r in resultados if not r["indexada"]]
    sin_indexar.sort(key=lambda fila: fila["url"])
    return {"total": len(urls), "indexadas": indexadas, "sin_indexar": sin_indexar}
