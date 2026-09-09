"""Sentry para el backend.

Vive en su propio módulo y no dentro de `settings.py` para poder testear la
decisión —inicializar o no, y con qué— sin importar la configuración entera de
Django.

Por qué existe: el 01-09-2026 el hilo que escribe un informe pago se cortó en
la sección 3 y no quedó rastro de por qué. El `logger.exception` iba a un
logger sin handler, los logs del contenedor se fueron con el deploy siguiente,
y el Sentry que estaba cableado era el de la web. La única señal de que algo
había fallado era la carta ofreciendo comprar de nuevo lo ya pagado.
"""

import sentry_sdk


def init_sentry(dsn: str, entorno: str, release: str | None) -> None:
    """Arranca Sentry si hay DSN. Sin DSN no hace nada: en desarrollo y en los
    tests la variable no está, y el arranque no puede depender de ella.

    `send_default_pii` queda apagado a propósito. Una carta natal lleva nombre,
    fecha, hora y lugar de nacimiento de una persona; mandarle eso a un tercero
    porque venía en el request es justo lo que no puede pasar.

    **`send_default_pii=False` no alcanza para eso, y creer que sí dejó el
    agujero abierto hasta el 09-09-2026.** Esa opción gobierna cookies y datos
    del usuario; el cuerpo del pedido lo gobierna `max_request_body_size`, que
    por defecto viene en `"medium"` — o sea, se manda. Y la integración de
    Django cuelga el procesador del request entero, así que basta un
    `logger.error` en cualquier vista para que el cuerpo salga adjunto: no hace
    falta una excepción. Medido: un pedido a `/api/webhooks/resend/` con un
    correo y un código en el cuerpo producía un evento que los llevaba a los
    dos. Por dónde dolía de verdad: `POST /api/auth/email` recibe
    `{email, codigo}`, y ese código de seis dígitos es una credencial de un solo
    uso que abre la cuenta.
    """
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        release=release,
        send_default_pii=False,
        # El cuerpo del pedido no viaja nunca. Ver el docstring: es una opción
        # aparte de `send_default_pii`, y sin ella el cuerpo se manda igual.
        max_request_body_size="never",
        # Sin performance tracing: lo que hace falta es enterarse de las
        # excepciones. Prender el muestreo cuesta cuota y no responde ninguna
        # pregunta que hoy tengamos.
        traces_sample_rate=0.0,
    )
