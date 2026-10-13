"""País del visitante por IP, y la moneda que le corresponde (RF2).

Base GeoLite2-Country de MaxMind en `GEOIP_PATH`, leída con `maxminddb` (el lector puro; el cliente
de alto nivel de MaxMind arrastra aiohttp y no hace falta). La consulta es en memoria (< 1 ms). Sin base, sin IP o con IP privada la
respuesta es «no sé» y la moneda cae a `usd`: la geo nunca puede ser la razón
de que una página no cargue. Nada de esto se guarda (política de privacidad:
la IP se usa para deducir el país y no se almacena).
"""

import ipaddress
import logging
import os
import threading

from django.conf import settings

from config.axes_ip import ip_del_cliente

logger = logging.getLogger(__name__)

#: Qué moneda ve cada país. Todo lo que no está acá es `usd`.
MONEDA_POR_PAIS = {"BR": "brl"}

_lock = threading.Lock()
_cargado: tuple[str, float] | None = None  # (ruta, mtime) de la base en memoria
_reader = None
_avisado = False


def _lector():
    """El `Reader` de maxminddb sobre la base actual, o None si no hay base.
    Se recarga sola si el archivo cambió (lo reemplaza `actualizar_geoip`)."""
    global _cargado, _reader, _avisado
    ruta = settings.GEOIP_PATH
    try:
        mtime = os.path.getmtime(ruta)
    except OSError:
        if not _avisado:
            logger.warning("sin base GeoLite2 en %s: la moneda inicial es usd para todos", ruta)
            _avisado = True
        return None
    with _lock:
        if _cargado != (ruta, mtime):
            import maxminddb

            if _reader is not None:
                _reader.close()
            _reader = maxminddb.open_database(ruta)
            _cargado = (ruta, mtime)
            _avisado = False
            logger.info("base GeoLite2 cargada: %s", ruta)
        return _reader


def recargar() -> None:
    """Olvida la base en memoria; la próxima consulta la vuelve a abrir."""
    global _cargado
    with _lock:
        _cargado = None


def pais_de(ip: str | None) -> str | None:
    """ISO 3166-1 alpha-2 de la IP, o None si no se puede saber."""
    if not ip:
        return None
    try:
        direccion = ipaddress.ip_address(ip)
    except ValueError:
        return None
    if direccion.is_private or direccion.is_loopback or direccion.is_link_local:
        return None
    lector = _lector()
    if lector is None:
        return None
    try:
        registro = lector.get(ip)
    except ValueError:  # maxminddb levanta ValueError con una IP que no parsea
        return None
    if not registro:
        return None
    return ((registro.get("country") or {}).get("iso_code")) or None


def moneda_para(pais: str | None) -> str:
    return MONEDA_POR_PAIS.get(pais or "", "usd")


def moneda_de(request) -> str:
    """La moneda inicial para esta request, por la IP real (última de
    `X-Forwarded-For`, la que escribe Traefik)."""
    return moneda_para(pais_de(ip_del_cliente(request)))
