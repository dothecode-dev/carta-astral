"""Cómo firma Polar, en un solo lugar.

Vivía copiado en los tres archivos de test del webhook, y los tres copiaban la
MISMA suposición equivocada: que el secreto viene con un prefijo `whsec_` y que
lo que se usa para el HMAC es su parte base64 decodificada. Con eso los tests
se validaban contra sí mismos —firmaban igual que verificaban— y pasaban en
verde mientras el endpoint rechazaba todas las entregas reales de Polar con un
403 (02-09-2026, el primer pago de prueba).

Lo que Polar hace de verdad es tratar el secreto como TEXTO PLANO OPACO: lo
base64-encodea entero, prefijo incluido, y la librería lo decodifica del otro
lado, así que la clave del HMAC son los bytes ASCII del secreto tal cual está
en el panel. Es lo que hace su SDK oficial en `validate_event`:

    base64_secret = base64.b64encode(secret.encode()).decode()
    webhook = Webhook(base64_secret)

`test_polar_firma_contrato.py` ancla eso contra el SDK de verdad, para que
esta afirmación no sea otra vez una suposición nuestra escrita en un docstring.
"""

import base64
import hashlib
import hmac
import time

# Con la derivación de Polar el prefijo no significa nada: es un carácter más
# del texto que se firma. Se lo deja porque es la forma que tiene el secreto
# real en producción, y así el test se parece a lo que corre.
SECRETO = "whsec_" + base64.b64encode(b"un-secreto-de-prueba-de-32-bytes").decode()


def llave(secreto: str) -> bytes:
    """La clave del HMAC: los bytes del secreto tal cual.

    Equivale a lo que la librería recupera cuando se le pasa
    `base64.b64encode(secreto)`, que es como hay que dárselo.
    """
    return secreto.encode()


def firmar(body: bytes, secreto: str = SECRETO, webhook_id: str = "msg_1", ts: str | None = None) -> dict[str, str]:
    """Las cabeceras de Standard Webhooks para `body`, firmadas como Polar."""
    ts = ts or str(int(time.time()))
    firmado = f"{webhook_id}.{ts}.".encode() + body
    firma = base64.b64encode(hmac.new(llave(secreto), firmado, hashlib.sha256).digest()).decode()
    return {
        "HTTP_WEBHOOK_ID": webhook_id,
        "HTTP_WEBHOOK_TIMESTAMP": ts,
        "HTTP_WEBHOOK_SIGNATURE": f"v1,{firma}",
    }


def firmar_a_la_vieja(body: bytes, secreto: str = SECRETO, webhook_id: str = "msg_1", ts: str | None = None) -> dict[str, str]:
    """La derivación equivocada que teníamos: sacarle el prefijo y decodificar.

    Existe para que un test pueda exigir que esto NO se acepte. Sin él, volver
    al bug sería un cambio silencioso: el resto de la suite seguiría en verde.
    """
    ts = ts or str(int(time.time()))
    clave = base64.b64decode(secreto.removeprefix("whsec_"))
    firmado = f"{webhook_id}.{ts}.".encode() + body
    firma = base64.b64encode(hmac.new(clave, firmado, hashlib.sha256).digest()).decode()
    return {
        "HTTP_WEBHOOK_ID": webhook_id,
        "HTTP_WEBHOOK_TIMESTAMP": ts,
        "HTTP_WEBHOOK_SIGNATURE": f"v1,{firma}",
    }
