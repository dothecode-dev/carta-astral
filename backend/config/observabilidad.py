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
    """
    if not dsn:
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=entorno,
        release=release,
        send_default_pii=False,
        # Sin performance tracing: lo que hace falta es enterarse de las
        # excepciones. Prender el muestreo cuesta cuota y no responde ninguna
        # pregunta que hoy tengamos.
        traces_sample_rate=0.0,
    )
