"""Avisos al admin por Telegram: disputas y rechazos del webhook de Stripe.

Un POST a `sendMessage` y nada más. NUNCA levanta: lo que avisa es siempre
más importante que el aviso, y un Telegram caído no puede cambiar la
respuesta de un webhook. Sin token configurado no hace nada —desarrollo y
tests— y lo dice una vez por proceso.

El token viaja en la URL, así que ningún log puede llevar la excepción de
httpx entera (`bing.py` tiene la misma trampa documentada): se loguea el tipo
y el status, nunca la URL.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
#: Tope de Telegram por mensaje.
_TOPE = 4000


def avisar_admin(texto: str) -> None:
    token = settings.TELEGRAM_BOT_TOKEN
    chat = settings.TELEGRAM_CHAT_ID
    if not token or not chat:
        logger.info("aviso al admin sin Telegram configurado: %s", texto[:200])
        return
    try:
        respuesta = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": texto[:_TOPE]},
            timeout=_TIMEOUT,
        )
    except Exception as exc:  # el contrato es «nunca levanta»
        # Amplio a propósito: `InvalidURL` y `StreamError` no heredan de
        # `HTTPError`, y una que escape convierte el 200 deliberado de un
        # webhook en un 5xx que Stripe reintenta en loop. Se loguea, no se
        # traga: sólo el tipo, porque el mensaje de httpx trae la URL con el
        # token.
        logger.warning("telegram no contestó: %s", type(exc).__name__)
        return
    if respuesta.status_code >= 400:
        logger.warning("telegram rechazó el aviso: %s", respuesta.status_code)
