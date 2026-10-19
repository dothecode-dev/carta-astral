"""Verificación de la firma de los webhooks de Mercado Pago.

Header `x-signature: ts=<epoch>,v1=<hex>`. El manifest firmado es
`id:<data.id en minúscula>;request-id:<x-request-id>;ts:<ts>;`, con HMAC-SHA256
en hexadecimal y el secreto del webhook. Si falta `data.id` o `x-request-id`
se omite ese par. No hay límite de antigüedad de `ts`: los reintentos llegan
con un `ts` nuevo y el webhook relee el pago desde la API, así que un replay
es inofensivo.

Función pura: sin Django ni HTTP. Un header mal formado devuelve False.
"""

import hashlib
import hmac
import re

_HEX64 = re.compile(r"[0-9a-fA-F]{64}")
_TS = re.compile(r"[0-9]+")


def _partes(x_signature: str) -> dict[str, str] | None:
    partes: dict[str, str] = {}
    for trozo in x_signature.split(","):
        clave, sep, valor = trozo.strip().partition("=")
        if not sep or clave in partes:
            return None
        partes[clave] = valor.strip()
    return partes


def verificar(x_signature: str, x_request_id: str, data_id: str, secreto: str) -> bool:
    if not isinstance(x_signature, str) or not x_signature:
        return False
    partes = _partes(x_signature)
    if partes is None:
        return False
    ts, v1 = partes.get("ts", ""), partes.get("v1", "")
    if not _TS.fullmatch(ts) or not _HEX64.fullmatch(v1):
        return False
    manifest = ""
    if data_id:
        manifest += f"id:{data_id.lower()};"
    if x_request_id:
        manifest += f"request-id:{x_request_id};"
    manifest += f"ts:{ts};"
    esperado = hmac.new(secreto.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1.lower())
