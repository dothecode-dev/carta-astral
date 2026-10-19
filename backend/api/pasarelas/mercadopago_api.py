"""Cliente HTTP de Mercado Pago: sólo habla con la API, sin modelos ni reglas.

El access token viaja en el header `Authorization`: nunca va a un log ni al
texto de una excepción. De un fallo de red sólo se loguea el tipo; de uno de
la API, el status y el método/ruta.
"""

import logging
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.mercadopago.com"
_TIMEOUT = httpx.Timeout(15.0)


class MPNoConfigurado(Exception):
    """Falta `MP_ACCESS_TOKEN`."""


class MPError(Exception):
    """Mercado Pago no contestó o rechazó el pedido. `status` es None si no hubo respuesta."""

    def __init__(self, mensaje: str, status: int | None = None):
        super().__init__(mensaje)
        self.status = status


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
        return r.json()
    except ValueError:
        raise MPError(
            "Mercado Pago devolvió una respuesta que no es JSON", status=r.status_code
        ) from None


def crear_preferencia(cuerpo: dict) -> dict:
    return _pedir("POST", "/checkout/preferences", json=cuerpo)


def obtener_pago(payment_id: str) -> dict:
    return _pedir("GET", f"/v1/payments/{payment_id}")


def buscar_pagos(external_reference: str) -> list[dict]:
    datos = _pedir("GET", "/v1/payments/search", params={"external_reference": external_reference})
    return datos.get("results", [])


def reembolsar(payment_id: str, idempotency_key: str) -> dict:
    return _pedir(
        "POST",
        f"/v1/payments/{payment_id}/refunds",
        json={},
        headers={"X-Idempotency-Key": idempotency_key},
    )


def obtener_contracargo(chargeback_id: str) -> dict:
    return _pedir("GET", f"/v1/chargebacks/{chargeback_id}")
