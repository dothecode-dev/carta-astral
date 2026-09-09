"""Todo lo que habla de la firma de los webhooks de Resend vive acá, y nada
más lo importa.

La capa HTTP (`webhooks_resend.py`) no conoce la librería: pide por esta
función. Mismo patrón que `stripe_client.py`.
"""

import logging
from collections.abc import Mapping

from standardwebhooks.webhooks import (
    EmptyWebhookSecretError,
    Webhook,
    WebhookVerificationError,
)

logger = logging.getLogger(__name__)


class FirmaInvalida(Exception):
    """La entrega no viene de Resend, o no viene entera."""


# Resend firma sus webhooks con Svix y manda las cabeceras `svix-id`,
# `svix-timestamp` y `svix-signature` (confirmado en
# resend.com/docs/dashboard/webhooks/verify-webhooks-requests, 09-09-2026).
# `standardwebhooks` implementa la especificación Standard Webhooks —que
# Svix mantiene y usa por dentro— con los nombres genéricos de esa spec:
# `Webhook.verify()` (site-packages/standardwebhooks/webhooks.py) busca
# literalmente `webhook-id`, `webhook-timestamp` y `webhook-signature` en el
# dict de cabeceras que se le pasa, sin forma de configurar otro nombre. Se
# remapean acá, antes de llamarla.
_REMAPEO_CABECERAS = {
    "svix-id": "webhook-id",
    "svix-timestamp": "webhook-timestamp",
    "svix-signature": "webhook-signature",
}


def verificar_firma(cuerpo: bytes, cabeceras: Mapping[str, str], secreto: str) -> dict:
    """Devuelve el evento (ya parseado) sólo si la firma y el timestamp son
    válidos.

    `cuerpo` son los BYTES exactos que llegaron (`request.body`), no el dict
    parseado: lo que Resend firma es `{svix-id}.{svix-timestamp}.{cuerpo}`, y
    volver a serializar el JSON puede dar otros bytes. La verificación la
    hace `standardwebhooks` —HMAC-SHA256 en base64 con comparación en tiempo
    constante y tolerancia de 5 minutos en el timestamp, fija en la
    librería—, que es código de seguridad que no tiene sentido reescribir.
    Los tests firman a mano, con el algoritmo de la documentación pública
    (`tests/api/resend_firma.py`), para que esto quede anclado a algo que no
    somos nosotros.

    El secreto llega con el formato `whsec_<base64>` que da el dashboard de
    Resend; la librería le saca el prefijo y decodifica el base64 sola.
    """
    remapeadas = {
        _REMAPEO_CABECERAS.get(k.lower(), k.lower()): v for k, v in cabeceras.items()
    }
    try:
        evento = Webhook(secreto).verify(cuerpo, remapeadas)
    except (WebhookVerificationError, EmptyWebhookSecretError, ValueError) as e:
        # El motivo, no sólo el rechazo: cabecera ausente, timestamp fuera de
        # tolerancia o firma que no coincide son problemas distintos. Son
        # mensajes fijos de la librería: no arrastran nada del payload.
        raise FirmaInvalida(str(e)) from e
    if not isinstance(evento, dict):
        # `verify()` con `json_parse=True` (el default) devuelve lo que salga
        # de `json.loads`: si el cuerpo era un JSON válido pero no un objeto
        # (una lista, un número), no hay `type` ni `data` que leer.
        raise FirmaInvalida("el cuerpo no es un objeto JSON")
    return evento
