"""De qué IP viene una request, detrás del proxy de Coolify.

django-axes bloquea por IP, y sin esto la lee de `REMOTE_ADDR`: la cadena de
`axes.helpers.get_client_ip_address` usa ipware sólo si está instalado (no lo
está) y, aun instalándolo, su `AXES_IPWARE_META_PRECEDENCE_ORDER` por defecto
es `("REMOTE_ADDR",)`. En este deploy todas las requests entran por Traefik y
`entrypoint.sh` arranca gunicorn plano, que no reescribe `REMOTE_ADDR`: sería
siempre la IP del contenedor del proxy. Con `AXES_LOCKOUT_PARAMETERS =
["ip_address"]` eso significa que los 5 intentos fallidos de cualquier bot
bloquean el admin para todo el mundo, el dueño incluido, durante una hora.
"""


def ip_del_cliente(request) -> str | None:
    """La IP real del cliente, o None si no hay ninguna en la request.

    `X-Forwarded-For` es una lista `cliente, proxy1, proxy2, ...` donde cada
    proxy agrega al final. El cliente puede mandar el header ya poblado con
    lo que se le ocurra, así que la primera entrada NO es confiable: quien
    quiera evadir el lockout manda `X-Forwarded-For: 1.2.3.4` y estrena IP en
    cada intento. La ÚLTIMA la escribe el último proxy de la cadena —acá
    Traefik— sobre lo que recibió, y esa sí es la conexión real que le llegó.

    Vale porque hay exactamente un proxy delante (Traefik en el mismo VPS). Si
    algún día se agrega otro —un CDN adelante, por ejemplo—, la última pasa a
    ser la del proxy intermedio y hay que contar desde el final tantas
    posiciones como proxies haya.
    """
    reenviadas = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if reenviadas:
        ultima = reenviadas.split(",")[-1].strip()
        if ultima:
            return ultima
    return request.META.get("REMOTE_ADDR")
