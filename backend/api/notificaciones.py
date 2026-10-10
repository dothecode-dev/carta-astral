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

import datetime
import logging

import httpx
from django.conf import settings

from api.firma_frases import nombre_signo
from api.mail_plantilla import Mail, Signo, render_html, render_texto

logger = logging.getLogger(__name__)

EVENTOS = ("informe_no_entregado", "compra_acreditada", "informe_en_curso", "informe_listo")

_API = "https://api.resend.com/emails"

# Se corta con el timeout puesto a mano: el default de httpx es no tener
# ninguno, y un aviso colgado del otro lado bloquearía el hilo que acaba de
# terminar un informe.
_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Los textos de cada aviso, por idioma. La forma —cabecera, tarjeta, botón,
# pie— la pone `mail_plantilla`; acá sólo hay palabras. `{url}` no aparece:
# el enlace lo arma `_armar` (la cuenta de esa persona, en su idioma, o la
# `ruta` del contexto, ver `_ruta`).
_TEXTOS = {
    # Genérico y siempre cierto: sale para cualquier compra acreditada que NO
    # dejó un informe escribiéndose (un pack, una que saldó deuda, una cuyo
    # arranque falló y queda para el reintento). Spec §11, RF24 v3.
    "compra_acreditada": {
        "es": {
            "asunto": "Recibimos tu pago", "eyebrow": "Pago recibido",
            "titulo": "Recibimos tu pago",
            "parrafos": ("Lo que compraste ya está en tu cuenta.",),
            "boton": "Ver mi cuenta",
            "motivo": "Recibís este mail porque hiciste una compra en astraguia.com.",
        },
        "en": {
            "asunto": "We received your payment", "eyebrow": "Payment received",
            "titulo": "We received your payment",
            "parrafos": ("What you bought is now in your account.",),
            "boton": "Go to my account",
            "motivo": "You're receiving this email because you made a purchase on astraguia.com.",
        },
        "pt": {
            "asunto": "Recebemos seu pagamento", "eyebrow": "Pagamento recebido",
            "titulo": "Recebemos seu pagamento",
            "parrafos": ("O que você comprou já está na sua conta.",),
            "boton": "Ver minha conta",
            "motivo": "Você recebe este e-mail porque fez uma compra em astraguia.com.",
        },
    },
    # Sólo cuando la compra SÍ dejó un informe escribiéndose; el aviso de que
    # terminó es `informe_listo`. El botón lleva a la cuenta (el contexto no
    # trae la ruta del informe): por eso no dice «Empezar a leer».
    "informe_en_curso": {
        "es": {
            "asunto": "Estamos escribiendo tu informe", "eyebrow": "Pago recibido",
            "titulo": "Ya estamos escribiendo tu informe",
            "parrafos": (
                "Tarda unos minutos: te mandamos otro mail cuando esté listo.",
            ),
            "boton": "Ver mi cuenta",
            "motivo": "Recibís este mail porque compraste un informe en astraguia.com.",
        },
        "en": {
            "asunto": "We're writing your report", "eyebrow": "Payment received",
            "titulo": "We're already writing your report",
            "parrafos": (
                "It takes a few minutes: we'll email you again when it's ready.",
            ),
            "boton": "Go to my account",
            "motivo": "You're receiving this email because you bought a report on astraguia.com.",
        },
        "pt": {
            "asunto": "Estamos escrevendo seu relatório", "eyebrow": "Pagamento recebido",
            "titulo": "Já estamos escrevendo seu relatório",
            "parrafos": (
                "Leva alguns minutos: mandamos outro e-mail quando estiver pronto.",
            ),
            "boton": "Ver minha conta",
            "motivo": "Você recebe este e-mail porque comprou um relatório em astraguia.com.",
        },
    },
    # Con la carta adentro (`_mail_informe_listo`): nombre, Sol/Luna/Ascendente
    # y el arranque. Si el contexto no trae nada de eso, queda el aviso simple.
    "informe_listo": {
        "es": {
            "asunto": "Tu informe está listo", "asunto_nombre": "Tu informe está listo, {nombre}",
            "eyebrow": "Informe natal · listo",
            "parrafos": ("Terminamos de escribir tu informe. Ya podés leerlo y bajarlo en PDF.",),
            "cita_rotulo": "Así empieza", "boton": "Seguir leyendo", "boton_simple": "Leer mi informe",
            "nota": "Ahí mismo también podés bajarlo en PDF.",
            "vinculo_asunto": "Tu informe de vínculo está listo",
            "vinculo_asunto_alias": "El informe de {a} y {b} está listo",
            "vinculo_eyebrow": "Informe de vínculo · listo",
            "motivo": "Recibís este mail porque pediste un informe en astraguia.com.",
        },
        "en": {
            "asunto": "Your report is ready", "asunto_nombre": "Your report is ready, {nombre}",
            "eyebrow": "Natal report · ready",
            "parrafos": ("We've finished writing your report. You can read it and download the PDF now.",),
            "cita_rotulo": "How it begins", "boton": "Keep reading", "boton_simple": "Read my report",
            "nota": "Right there you can also download it as a PDF.",
            "vinculo_asunto": "Your relationship report is ready",
            "vinculo_asunto_alias": "The report for {a} and {b} is ready",
            "vinculo_eyebrow": "Relationship report · ready",
            "motivo": "You're receiving this email because you requested a report on astraguia.com.",
        },
        "pt": {
            "asunto": "Seu relatório está pronto", "asunto_nombre": "Seu relatório está pronto, {nombre}",
            "eyebrow": "Relatório natal · pronto",
            "parrafos": ("Terminamos de escrever seu relatório. Você já pode lê-lo e baixar o PDF.",),
            "cita_rotulo": "Assim começa", "boton": "Continuar lendo", "boton_simple": "Ler meu relatório",
            "nota": "Lá mesmo você também pode baixá-lo em PDF.",
            "vinculo_asunto": "Seu relatório de vínculo está pronto",
            "vinculo_asunto_alias": "O relatório de {a} e {b} está pronto",
            "vinculo_eyebrow": "Relatório de vínculo · pronto",
            "motivo": "Você recebe este e-mail porque pediu um relatório em astraguia.com.",
        },
    },
    "informe_no_entregado": {
        "es": {
            "asunto": "No pudimos terminar tu informe", "eyebrow": "Aviso",
            "titulo": "No pudimos terminar tu informe",
            "parrafos": (
                "Algo falló de nuestro lado. Ya te devolvimos el informe a tu cuenta: no "
                "se te cobró de nuevo y podés volver a pedirlo cuando quieras.",
                "Perdón por la espera.",
            ),
            "boton": "Ver mi cuenta",
            "motivo": "Recibís este mail porque pediste un informe en astraguia.com.",
        },
        "en": {
            "asunto": "We couldn't finish your report", "eyebrow": "Notice",
            "titulo": "We couldn't finish your report",
            "parrafos": (
                "Something failed on our side. We've credited the report back to your "
                "account: you weren't charged again and you can request it whenever you like.",
                "Sorry for the wait.",
            ),
            "boton": "Go to my account",
            "motivo": "You're receiving this email because you requested a report on astraguia.com.",
        },
        "pt": {
            "asunto": "Não conseguimos terminar seu relatório", "eyebrow": "Aviso",
            "titulo": "Não conseguimos terminar seu relatório",
            "parrafos": (
                "Algo falhou do nosso lado. Devolvemos o relatório para a sua conta: você "
                "não foi cobrado de novo e pode pedir de novo quando quiser.",
                "Desculpe pela espera.",
            ),
            "boton": "Ver minha conta",
            "motivo": "Você recebe este e-mail porque pediu um relatório em astraguia.com.",
        },
    },
}

_LANG_DEFAULT = "es"

# El código de acceso todavía no tiene `Account` —se crea recién al
# canjear—, así que su texto vive aparte de `_TEXTOS`: lleva `{codigo}` y
# `{ttl}`, y no pasa por la validación de `EVENTOS` porque no se manda con
# `notificar`.
_TEXTOS_CODIGO = {
    "es": {
        "asunto": "Tu código de acceso es {codigo}", "eyebrow": "Código de acceso",
        "titulo": "Tu código para entrar",
        "parrafos": ("Copialo en la pantalla donde lo pediste.",),
        "nota": "Vence en {ttl} minutos. Si no lo pediste vos, ignorá este mail: nadie "
                "puede entrar sin el código.",
        "motivo": "Recibís este mail porque alguien pidió un código para entrar a "
                  "astraguia.com con esta dirección.",
    },
    "en": {
        "asunto": "Your access code is {codigo}", "eyebrow": "Access code",
        "titulo": "Your sign-in code",
        "parrafos": ("Enter it on the screen where you asked for it.",),
        "nota": "It expires in {ttl} minutes. If you didn't request it, ignore this "
                "email: no one can sign in without the code.",
        "motivo": "You're receiving this email because someone asked for a code to sign "
                  "in to astraguia.com with this address.",
    },
    "pt": {
        "asunto": "Seu código de acesso é {codigo}", "eyebrow": "Código de acesso",
        "titulo": "Seu código para entrar",
        "parrafos": ("Digite-o na tela onde você o pediu.",),
        "nota": "Ele expira em {ttl} minutos. Se você não pediu, ignore este e-mail: "
                "ninguém consegue entrar sem o código.",
        "motivo": "Você recebe este e-mail porque alguém pediu um código para entrar em "
                  "astraguia.com com este endereço.",
    },
}

# Para la fecha de nacimiento del mail de «informe listo».
_MESES = {
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"),
    "pt": ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
           "setembro", "outubro", "novembro", "dezembro"),
}
_FECHA = {"es": "{d} de {m} de {a}", "en": "{m} {d}, {a}", "pt": "{d} de {m} de {a}"}

_ROTULOS_SIGNO = {
    "es": {"Sun": "Sol", "Moon": "Luna", "Ascendant": "Ascendente"},
    "en": {"Sun": "Sun", "Moon": "Moon", "Ascendant": "Rising"},
    "pt": {"Sun": "Sol", "Moon": "Lua", "Ascendant": "Ascendente"},
}
_GLIFOS = {"Sun": "☉", "Moon": "☽", "Ascendant": "AC"}

# Cuánto se queda de lo que escribió una persona (el nombre de la carta, el
# lugar, un alias) en el asunto y en el cuerpo: lo justo para saludar.
_NOMBRE_MAX = 40
_LUGAR_MAX = 80
_PREHEADER_MAX = 110


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


def _armar_codigo(lang: str, codigo: str) -> tuple[str, str, str]:
    if lang not in _TEXTOS_CODIGO:
        lang = _LANG_DEFAULT
    t = _TEXTOS_CODIGO[lang]
    ttl = settings.CODIGO_TTL_MINUTOS
    asunto = t["asunto"].format(codigo=codigo)
    nota = t["nota"].format(ttl=ttl)
    mail = Mail(
        preheader=nota, eyebrow=t["eyebrow"], titulo=t["titulo"], parrafos=t["parrafos"],
        codigo=codigo, nota=nota, motivo=t["motivo"],
    )
    return asunto, _html(mail, lang), render_texto(mail, lang)


def textos_codigo(lang: str, codigo: str) -> tuple[str, str]:
    """Asunto y cuerpo del mail del código de acceso, en el idioma pedido (o
    español si no hay traducción). El código va en el asunto a propósito: se
    lee desde la notificación del teléfono sin abrir el mail. El TTL sale de
    `settings.CODIGO_TTL_MINUTOS`, no está fijo en el texto: si cambia la
    config, el mail lo sigue."""
    asunto, html, _ = _armar_codigo(lang, codigo)
    return asunto, html


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

    asunto, html, texto = _armar_codigo(lang, codigo)
    try:
        respuesta = _post_resend(email, asunto, html, texto)
    except Exception as exc:
        logger.exception("fallo el envio %s", "codigo_acceso")
        raise EnvioFallido("fallo el envio a Resend") from exc

    # El mail YA SALIÓ (2xx): lo que sigue es sólo cosmético para el log, y
    # un id que no se puede leer (body vacío o no-JSON) no puede convertir un
    # envío exitoso en un `EnvioFallido` — eso le gastaría el cupo de la hora
    # a alguien que ya tiene el código en la bandeja.
    try:
        resend_id = respuesta.json().get("id")
    except Exception:
        resend_id = None
    logger.info(
        "aviso enviado",
        extra={"evento": "codigo_acceso", "resend_id": resend_id},
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
    url = f"{settings.WEB_BASE_URL.rstrip('/')}/{lang}{_ruta(contexto)}"
    asunto, html, texto = _armar(evento, contexto, lang, url)

    respuesta = _post_resend(account.email, asunto, html, texto)
    logger.info(
        "aviso enviado",
        extra={"evento": evento, "account": account.pk, "resend_id": respuesta.json().get("id")},
    )


def _html(mail: Mail, lang: str) -> str:
    return render_html(mail, lang, f"{settings.WEB_BASE_URL.rstrip('/')}/apple-icon.png")


def _armar(evento: str, contexto: dict, lang: str, url: str) -> tuple[str, str, str]:
    """Asunto, HTML y texto plano de un aviso. Función pura sobre
    `(evento, contexto, lang, url)`: es donde se verifica todo el mail sin
    mandar nada."""
    if lang not in _TEXTOS[evento]:
        lang = _LANG_DEFAULT
    if evento == "informe_listo":
        asunto, mail = _mail_informe_listo(contexto, lang, url)
    else:
        t = _TEXTOS[evento][lang]
        asunto = t["asunto"]
        mail = Mail(
            preheader=t["parrafos"][0], eyebrow=t["eyebrow"], titulo=t["titulo"],
            parrafos=t["parrafos"], boton=t["boton"], url=url, motivo=t["motivo"],
        )
    return asunto, _html(mail, lang), render_texto(mail, lang)


def _limpio(valor, tope: int) -> str:
    """Un texto de una persona para ponerlo en un asunto o un encabezado: sin
    saltos ni espacios repetidos (nada que pueda partir una cabecera) y
    acotado."""
    if not isinstance(valor, str):
        return ""
    texto = " ".join(valor.split())
    return texto if len(texto) <= tope else texto[: tope - 1].rstrip() + "…"


def _fecha(valor, lang: str) -> str:
    if not isinstance(valor, str):
        return ""
    try:
        d = datetime.date.fromisoformat(valor)
    except ValueError:
        return ""
    return _FECHA[lang].format(d=d.day, m=_MESES[lang][d.month - 1], a=d.year)


def _signos(contexto: dict, lang: str) -> tuple[Signo, ...]:
    """Sol, Luna y Ascendente en palabras. Lo que no sea un cuerpo y un signo
    conocidos se descarta: el contexto no es de fiar sólo por venir de adentro."""
    signos = []
    for par in contexto.get("signos") or ():
        try:
            cuerpo, signo = par
            signos.append(Signo(_GLIFOS[cuerpo], _ROTULOS_SIGNO[lang][cuerpo], nombre_signo(signo, lang)))
        except (KeyError, ValueError, TypeError):
            continue
    return tuple(signos)


def _mail_informe_listo(contexto: dict, lang: str, url: str) -> tuple[str, Mail]:
    t = _TEXTOS["informe_listo"][lang]
    arranque = contexto.get("arranque") if isinstance(contexto.get("arranque"), str) else ""
    if contexto.get("vinculo"):
        alias = [_limpio(a, _NOMBRE_MAX) for a in (contexto.get("alias") or ())][:2]
        alias += [""] * (2 - len(alias))
        if alias[0] and alias[1]:
            asunto = t["vinculo_asunto_alias"].format(a=alias[0], b=alias[1])
        else:
            asunto = t["vinculo_asunto"]
        eyebrow, signos, detalle = t["vinculo_eyebrow"], (), ""
    else:
        nombre = _limpio(contexto.get("nombre"), _NOMBRE_MAX)
        asunto = t["asunto_nombre"].format(nombre=nombre) if nombre else t["asunto"]
        eyebrow, signos = t["eyebrow"], _signos(contexto, lang)
        detalle = " · ".join(
            x for x in (_fecha(contexto.get("fecha"), lang), _limpio(contexto.get("lugar"), _LUGAR_MAX)) if x
        )
    mail = Mail(
        # La bandeja muestra unos 100 caracteres al lado del asunto.
        preheader=_limpio(arranque, _PREHEADER_MAX) or t["parrafos"][0], eyebrow=eyebrow, titulo=asunto, detalle=detalle,
        signos=signos,
        # Con arranque, el arranque ES el cuerpo; sin él, el aviso simple.
        parrafos=() if arranque else t["parrafos"],
        cita_rotulo=t["cita_rotulo"] if arranque else "", cita=arranque,
        # Sin arranque no hay nada que «seguir»: el botón de siempre.
        boton=t["boton"] if arranque else t["boton_simple"], url=url,
        nota=t["nota"], motivo=t["motivo"],
    )
    return asunto, mail


def _ruta(contexto: dict) -> str:
    """A dónde lleva el botón del mail, dentro del sitio y del idioma: la
    `ruta` del contexto (p. ej. `/carta/<uuid>` para `informe_listo`) o la
    cuenta. Sólo un path propio («/x», no «//host»): el link sale con
    nuestra firma y no puede apuntar afuera."""
    ruta = contexto.get("ruta")
    if isinstance(ruta, str) and ruta.startswith("/") and not ruta.startswith("//"):
        return ruta
    return "/cuenta"


def _post_resend(direccion: str, asunto: str, html: str, texto: str = "") -> httpx.Response:
    """El POST a Resend, compartido por `_enviar` (con cuenta) y
    `enviar_codigo` (con una dirección suelta). `texto` es la versión en texto
    plano: los clientes sin HTML la muestran y pesa a favor de la entrega."""
    cuerpo = {"from": settings.MAIL_FROM, "to": [direccion], "subject": asunto, "html": html}
    if texto:
        cuerpo["text"] = texto
    respuesta = httpx.post(
        _API,
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json=cuerpo,
        timeout=_TIMEOUT,
    )
    respuesta.raise_for_status()
    return respuesta
