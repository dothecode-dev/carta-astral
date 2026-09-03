"""Avisos al usuario por mail.

Sale por la API HTTP de Resend, con `httpx` y nada más: es un POST con un JSON
y no justifica un SDK. Se eligió Resend por lo mismo que se elige un proveedor
para esto —que el mail llegue sin montar infraestructura—: 3.000 mensajes por
mes sin cargo alcanzan de sobra para el volumen de hoy, y el DNS del dominio ya
está en Route 53.

**El remitente va en un subdominio** (`send.astraguia.com`, `MAIL_FROM`), no en
`astraguia.com` a secas: el dominio raíz tiene el SPF de ImprovMX, que es lo
que hace andar el correo ENTRANTE, y meterle el include de otro proveedor es la
forma clásica de romper las dos cosas a la vez.

Nunca propaga una excepción. Esto corre DESPUÉS de mover plata —acreditar una
compra, devolver el derecho de un informe que no se pudo entregar—, así que un
fallo del proveedor no puede revertir la devolución ni dejar el webhook de
Stripe en 5xx, que haría que Stripe reintente una compra ya acreditada.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

EVENTOS = ("informe_no_entregado", "compra_acreditada")

_API = "https://api.resend.com/emails"

# Se corta con el timeout puesto a mano: el default de httpx es no tener
# ninguno, y un aviso colgado del otro lado bloquearía el hilo que acaba de
# terminar un informe.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Mismo patrón que los DISCLAIMERS de `interpretation_service`: un dict por
# idioma en el módulo. `{url}` es la cuenta de esa persona, en su idioma.
_TEXTOS = {
    "compra_acreditada": {
        "es": (
            "Tu compra está lista",
            "<p>Recibimos tu pago y ya tenés el informe disponible en tu cuenta.</p>"
            '<p><a href="{url}">Ver mi cuenta</a></p>',
        ),
        "en": (
            "Your purchase is ready",
            "<p>We received your payment and your report is now available in your account.</p>"
            '<p><a href="{url}">Go to my account</a></p>',
        ),
        "pt": (
            "Sua compra está pronta",
            "<p>Recebemos seu pagamento e o relatório já está disponível na sua conta.</p>"
            '<p><a href="{url}">Ver minha conta</a></p>',
        ),
    },
    "informe_no_entregado": {
        "es": (
            "No pudimos terminar tu informe",
            "<p>Algo falló de nuestro lado y no pudimos terminar de escribir tu informe. "
            "Te devolvimos el informe a tu cuenta: no se te cobró de nuevo y podés "
            "volver a pedirlo cuando quieras.</p>"
            '<p><a href="{url}">Ver mi cuenta</a></p>',
        ),
        "en": (
            "We couldn't finish your report",
            "<p>Something failed on our side and we couldn't finish writing your report. "
            "We've credited it back to your account: you weren't charged again and you "
            "can request it whenever you like.</p>"
            '<p><a href="{url}">Go to my account</a></p>',
        ),
        "pt": (
            "Não conseguimos terminar seu relatório",
            "<p>Algo falhou do nosso lado e não conseguimos terminar de escrever seu "
            "relatório. Devolvemos o relatório para a sua conta: você não foi cobrado de "
            "novo e pode pedir de novo quando quiser.</p>"
            '<p><a href="{url}">Ver minha conta</a></p>',
        ),
    },
}

_LANG_DEFAULT = "es"


def notificar(account, evento: str, contexto: dict, lang: str) -> None:
    if evento not in EVENTOS:
        raise ValueError(f"evento desconocido: {evento!r}")
    try:
        _enviar(account, evento, contexto, lang)
    except Exception:
        logger.exception("fallo el aviso %s a la cuenta %s", evento, account.pk)


def _enviar(account, evento, contexto, lang):
    logger.info(
        "aviso al usuario", extra={"evento": evento, "account": account.pk, "lang": lang},
    )
    # Sin proveedor configurado (desarrollo, y los tests de todo lo demás) el
    # aviso queda en el log y ya: no es un fallo, es que no hay a dónde mandarlo.
    if not settings.RESEND_API_KEY:
        return
    # Una cuenta puede no tener mail: las de Apple con "ocultar mi correo" y las
    # de desarrollo. Tampoco es un fallo.
    if not account.email:
        logger.info("aviso sin destinatario", extra={"account": account.pk, "evento": evento})
        return

    if lang not in _TEXTOS[evento]:
        lang = _LANG_DEFAULT
    asunto, html = _TEXTOS[evento][lang]
    url = f"{settings.WEB_BASE_URL.rstrip('/')}/{lang}/cuenta"

    respuesta = httpx.post(
        _API,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": settings.MAIL_FROM,
            "to": [account.email],
            "subject": asunto,
            "html": html.format(url=url),
        },
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    logger.info(
        "aviso enviado",
        extra={"evento": evento, "account": account.pk, "resend_id": respuesta.json().get("id")},
    )
