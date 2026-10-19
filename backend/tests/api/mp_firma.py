"""Firma de webhooks de Mercado Pago, armada a mano según su documentación.

Producción verifica con `api.pasarelas.mercadopago_firma`. Acá se firma con el
algoritmo documentado (header `x-signature: ts=...,v1=...`; manifest
`id:<data.id>;request-id:<x-request-id>;ts:<ts>;`; HMAC-SHA256 en hexadecimal
con el secreto del webhook), SIN importar el código de producción. Es la
lección de `stripe_firma.py`: si firmar y verificar comparten una derivación
equivocada, la suite pasa y ningún pago real valida.
"""

import hashlib
import hmac
import time

SECRETO = "mp_secreto_de_prueba_" + "z" * 32


def firmar(
    data_id: str,
    request_id: str,
    ts: int | None = None,
    secreto: str = SECRETO,
) -> str:
    """El header `x-signature` para ese `data.id` y `x-request-id`."""
    marca = int(time.time()) if ts is None else ts
    manifest = ""
    if data_id:
        manifest += f"id:{data_id.lower()};"
    if request_id:
        manifest += f"request-id:{request_id};"
    manifest += f"ts:{marca};"
    v1 = hmac.new(secreto.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return f"ts={marca},v1={v1}"
