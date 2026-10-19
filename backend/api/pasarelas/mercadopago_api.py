"""Cliente HTTP de Mercado Pago: sólo habla con la API, sin modelos ni reglas.

El access token viaja en el header `Authorization`: nunca va a un log ni al
texto de una excepción. De un fallo de red sólo se loguea el tipo; de uno de
la API, el status y el método/ruta.
"""

import datetime as dt
import logging
import re
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mercadopago.com"
_TIMEOUT = httpx.Timeout(15.0)
_ID_VALIDO = re.compile(r"[A-Za-z0-9_-]+")


class MPNoConfigurado(Exception):
    """Falta `MP_ACCESS_TOKEN`."""


class MPError(Exception):
    """Mercado Pago no contestó o rechazó el pedido. `status` es None si no hubo respuesta."""

    def __init__(self, mensaje: str, status: int | None = None):
        super().__init__(mensaje)
        self.status = status


def id_valido(valor: str) -> bool:
    """Si `valor` puede ir como segmento de ruta (ver `_seg`). Para que quien
    llama distinga un id que nunca va a servir —definitivo— de un fallo de MP."""
    return bool(_ID_VALIDO.fullmatch(str(valor)))


def _seg(valor: str) -> str:
    """Valida un id que viene de un webhook antes de usarlo como segmento de ruta.

    Sólo `[A-Za-z0-9_-]`: escapar no alcanza, `.` y `..` siguen siendo un
    segmento que httpx normaliza hacia otra ruta. Si no cumple, no hay pedido.
    """
    texto = str(valor)
    if not id_valido(texto):
        raise MPError("id inválido")
    return texto


def _cliente() -> httpx.Client:
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}"},
        timeout=_TIMEOUT,
    )


def _pedir(
    metodo: str,
    ruta: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
    headers: dict | None = None,
) -> Any:
    if not settings.MP_ACCESS_TOKEN:
        raise MPNoConfigurado("MP_ACCESS_TOKEN no está configurado")
    try:
        with _cliente() as cliente:
            r = cliente.request(metodo, ruta, json=json, params=params, headers=headers)
    except httpx.HTTPError as exc:
        # Sólo el tipo: el texto de httpx puede traer la URL y los headers.
        logger.warning("mercadopago no contestó: %s %s (%s)", metodo, ruta, type(exc).__name__)
        raise MPError(f"Mercado Pago no contestó ({type(exc).__name__})") from None
    if r.status_code >= 400:
        logger.warning("mercadopago rechazó: %s %s -> %s", metodo, ruta, r.status_code)
        raise MPError(f"Mercado Pago respondió {r.status_code}", status=r.status_code)
    try:
        datos = r.json()
    except ValueError:
        raise MPError(
            "Mercado Pago devolvió una respuesta que no es JSON", status=r.status_code
        ) from None
    if not isinstance(datos, dict):
        raise MPError("Mercado Pago devolvió JSON que no es un objeto", status=r.status_code)
    return datos


def crear_preferencia(cuerpo: dict) -> dict:
    return _pedir("POST", "/checkout/preferences", json=cuerpo)


def obtener_pago(payment_id: str) -> dict:
    return _pedir("GET", f"/v1/payments/{_seg(payment_id)}")


def buscar_pagos(external_reference: str) -> list[dict]:
    datos = _pedir("GET", "/v1/payments/search", params={"external_reference": external_reference})
    return datos.get("results", [])


#: Pagos por página de `buscar_pagos_actualizados`, y tope de páginas: con el
#: volumen de ASTRA una ventana de horas no llega ni a una.
_POR_PAGINA = 100
_MAX_PAGINAS = 50


def _fecha(momento: dt.datetime) -> str:
    """El formato que acepta MP (`yyyy-MM-dd'T'HH:mm:ss.SSSZ`), en UTC."""
    utc = momento.astimezone(dt.UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def buscar_pagos_actualizados(desde: dt.datetime, hasta: dt.datetime) -> list[dict]:
    """Todos los pagos de la cuenta modificados entre `desde` y `hasta`.

    Verificado contra el sandbox el 19-10-2026: `range=date_last_updated` con
    `begin_date`/`end_date` filtra por la última modificación (un pago creado
    antes y reembolsado dentro de la ventana aparece; por `date_created` no),
    y `paging` trae `total`, `offset` y `limit`.
    """
    pagos: list[dict] = []
    for pagina in range(_MAX_PAGINAS):
        datos = _pedir("GET", "/v1/payments/search", params={
            "sort": "date_last_updated", "criteria": "asc", "range": "date_last_updated",
            "begin_date": _fecha(desde), "end_date": _fecha(hasta),
            "limit": _POR_PAGINA, "offset": pagina * _POR_PAGINA,
        })
        resultados = datos.get("results")
        if not isinstance(resultados, list):
            raise MPError("Mercado Pago devolvió `results` que no es una lista")
        pagos.extend(resultados)
        paging = datos.get("paging") if isinstance(datos.get("paging"), dict) else {}
        total = paging.get("total")
        if not resultados or not isinstance(total, int) or len(pagos) >= total:
            return pagos
    logger.warning("mercadopago: más de %s páginas de pagos actualizados; se corta", _MAX_PAGINAS)
    return pagos


def reembolsar(payment_id: str, idempotency_key: str) -> dict:
    return _pedir(
        "POST",
        f"/v1/payments/{_seg(payment_id)}/refunds",
        json={},
        headers={"X-Idempotency-Key": idempotency_key},
    )


def obtener_contracargo(chargeback_id: str) -> dict:
    return _pedir("GET", f"/v1/chargebacks/{_seg(chargeback_id)}")
