"""Avisos al usuario por mail.

Sale por la API HTTP de Resend, con `httpx` y nada más: es un POST con un JSON
y no justifica un SDK. Se eligió Resend por lo mismo que se elige un proveedor
para esto —que el mail llegue sin montar infraestructura—: 3.000 mensajes por
mes sin cargo alcanzan de sobra para el volumen de hoy, y el DNS del dominio ya
está en Route 53.

**El remitente es `info@astraguia.com`** (`MAIL_FROM`), la misma dirección que
el sitio publica en el pie y en los legales: un aviso de compra que llega desde
otra dirección se lee como si fuera de otro.

Eso no obliga a tocar el SPF —un registro admite varios `include:`, y el de
ImprovMX quedó igual—, pero sí obliga a NO cargar el MX que Resend ofrece para
la raíz: viene con prioridad 9 contra el 10 de ImprovMX y se llevaría todo el
correo entrante. Sin ese MX se envía igual.

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

# El código de acceso todavía no tiene `Account` —se crea recién al
# canjear—, así que su texto vive aparte de `_TEXTOS`: el placeholder es
# `{codigo}`, no `{url}`, y no pasa por la validación de `EVENTOS` porque no
# se manda con `notificar`.
_TEXTOS_CODIGO = {
    "es": (
        "Tu código de acceso es {codigo}",
        "<p>Usá este código para entrar a tu cuenta: <strong>{codigo}</strong></p>"
        "<p>Vence en {ttl} minutos. Si no lo pediste vos, ignorá este mail.</p>",
    ),
    "en": (
        "Your access code is {codigo}",
        "<p>Use this code to sign in to your account: <strong>{codigo}</strong></p>"
        "<p>It expires in {ttl} minutes. If you didn't request it, ignore this email.</p>",
    ),
    "pt": (
        "Seu código de acesso é {codigo}",
        "<p>Use este código para entrar na sua conta: <strong>{codigo}</strong></p>"
        "<p>Ele expira em {ttl} minutos. Se você não pediu, ignore este e-mail.</p>",
    ),
}


class EnvioFallido(Exception):
    """El mail del código de acceso no salió —sin clave configurada o falló
    el POST a Resend— y quien llama tiene que enterarse: a diferencia de los
    eventos de `notificar`, que son avisos accesorios de algo que ya pasó y
    la persona puede ver igual entrando a la cuenta, acá el mail ES el
    mecanismo de acceso. Tragar esto encierra afuera a alguien que espera un
    código que nunca va a llegar, con el cupo de la hora ya gastado y sin una
    sola señal en ningún lado. El mensaje nunca lleva el código ni la
    dirección."""


def notificar(account, evento: str, contexto: dict, lang: str) -> None:
    if evento not in EVENTOS:
        raise ValueError(f"evento desconocido: {evento!r}")
    try:
        _enviar(account, evento, contexto, lang)
    except Exception:
        logger.exception("fallo el aviso %s a la cuenta %s", evento, account.pk)


def textos_codigo(lang: str, codigo: str) -> tuple[str, str]:
    """Asunto y cuerpo del mail del código de acceso, en el idioma pedido (o
    español si no hay traducción). El código va en el asunto a propósito: se
    lee desde la notificación del teléfono sin abrir el mail. El TTL sale de
    `settings.CODIGO_TTL_MINUTOS`, no está fijo en el texto: si cambia la
    config, el mail lo sigue."""
    if lang not in _TEXTOS_CODIGO:
        lang = _LANG_DEFAULT
    asunto, html = _TEXTOS_CODIGO[lang]
    ttl = settings.CODIGO_TTL_MINUTOS
    return asunto.format(codigo=codigo), html.format(codigo=codigo, ttl=ttl)


def enviar_codigo(email: str, codigo: str, lang: str) -> None:
    """Hermana de `notificar` en la firma, no en el criterio de fallo
    (Ruling 13): cuando se manda el código de acceso todavía no hay
    `Account` a la que atarlo —se crea recién al canjear—, así que recibe la
    dirección directo. Pero a diferencia de `notificar`, acá el mail ES el
    mecanismo de acceso, así que un fallo del proveedor —incluida la
    ausencia de `RESEND_API_KEY`, sin distinguir por entorno— se propaga como
    `EnvioFallido`. Decidir qué hacer con eso (revertir el envío contabilizado,
    devolver 503) es tarea de quien llama, no de esta función. Nunca el
    código ni la dirección van al log ni al mensaje de la excepción."""
    logger.info("aviso al usuario", extra={"evento": "codigo_acceso", "lang": lang})
    if not settings.RESEND_API_KEY:
        raise EnvioFallido("sin RESEND_API_KEY configurada")

    asunto, html = textos_codigo(lang, codigo)
    try:
        respuesta = _post_resend(email, asunto, html)
    except Exception as exc:
        logger.exception("fallo el envio %s", "codigo_acceso")
        raise EnvioFallido("fallo el envio a Resend") from exc

    logger.info(
        "aviso enviado",
        extra={"evento": "codigo_acceso", "resend_id": respuesta.json().get("id")},
    )


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

    respuesta = _post_resend(account.email, asunto, html.format(url=url))
    logger.info(
        "aviso enviado",
        extra={"evento": evento, "account": account.pk, "resend_id": respuesta.json().get("id")},
    )


def _post_resend(direccion: str, asunto: str, html: str) -> httpx.Response:
    """El POST a Resend, compartido por `_enviar` (con cuenta) y
    `enviar_codigo` (con una dirección suelta)."""
    respuesta = httpx.post(
        _API,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json={
            "from": settings.MAIL_FROM,
            "to": [direccion],
            "subject": asunto,
            "html": html,
        },
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    return respuesta
