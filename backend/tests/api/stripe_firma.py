"""Firma de webhooks de Stripe, armada a mano según su documentación pública.

Del lado de producción verifica la librería oficial (`stripe.Webhook`). Acá se
firma con el algoritmo documentado —HMAC-SHA256 sobre `{timestamp}.{cuerpo}`,
en hexadecimal, en el header `Stripe-Signature`—, no con un helper de la misma
librería. Esa asimetría es a propósito: es la lección del 02-09-2026, cuando
firmábamos y verificábamos con la MISMA derivación equivocada de la clave de
Polar y ningún pago real podía validar con la suite entera en verde. Si la
librería y la documentación divergen, estos tests se ponen rojos.
"""

import hashlib
import hmac
import time

SECRETO = "whsec_" + "z" * 32


def firmar(cuerpo: bytes, secreto: str = SECRETO, timestamp: int | None = None) -> str:
    """El header `Stripe-Signature` para ese cuerpo exacto."""
    ts = int(time.time()) if timestamp is None else timestamp
    firmado = f"{ts}.".encode() + cuerpo
    v1 = hmac.new(secreto.encode(), firmado, hashlib.sha256).hexdigest()
    return f"t={ts},v1={v1}"
