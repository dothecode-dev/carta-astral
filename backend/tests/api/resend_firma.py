"""Firma de webhooks de Resend, armada a mano según la especificación
Standard Webhooks (la que Svix mantiene y usa por dentro, y la que Resend
usa para firmar sus entregas).

Del lado de producción verifica la librería `standardwebhooks`
(`api/resend_client.py`). Acá se firma con el algoritmo documentado —
HMAC-SHA256 sobre `{svix-id}.{svix-timestamp}.{cuerpo}`, en BASE64 (no
hexadecimal), con el secreto `whsec_<base64>` sin el prefijo y decodificado
de base64—, no con un helper de la misma librería. Esa asimetría es a
propósito: es la lección de `tests/api/stripe_firma.py`, escrita después de
un incidente real con Polar donde firma y verificación compartían la misma
derivación equivocada de la clave y ningún pago real podía validar con la
suite entera en verde. Si la librería y la documentación divergen, estos
tests se ponen rojos.
"""

import base64
import hashlib
import hmac
import time

# 24 bytes crudos -> 32 caracteres base64 sin relleno, para que las pruebas
# de "padding" que hace la librería (agrega "==" de más) no escondan un bug.
SECRETO = "whsec_" + base64.b64encode(b"z" * 24).decode()

MSG_ID = "msg_test_1"


def firmar(
    cuerpo: bytes,
    secreto: str = SECRETO,
    msg_id: str = MSG_ID,
    timestamp: int | None = None,
) -> dict[str, str]:
    """Las tres cabeceras `svix-*` para ese cuerpo exacto."""
    ts = int(time.time()) if timestamp is None else timestamp
    clave = base64.b64decode(secreto.removeprefix("whsec_") + "==")
    firmado = f"{msg_id}.{ts}.".encode() + cuerpo
    firma = base64.b64encode(hmac.new(clave, firmado, hashlib.sha256).digest()).decode()
    return {
        "svix-id": msg_id,
        "svix-timestamp": str(ts),
        "svix-signature": f"v1,{firma}",
    }
