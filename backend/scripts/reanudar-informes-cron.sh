#!/bin/sh
# Termina los informes que quedaron a medias. Lo dispara el cron del VPS de
# producción cada 2 minutos; ver la instalación al pie.
#
# Por qué existe un cron y no basta el hilo del request: `completar_generacion`
# hace UN intento y muere con él. Si una sección falla —un timeout, un techo de
# tokens corto—, la fila queda `completa=False` con el derecho ya consumido y
# nada la vuelve a llamar: `INTENTOS_MAXIMOS` se gastaba de a un intento por
# vida. Pasó el 01-09-2026 con el informe de la carta 8.
#
# Por qué acá y no en las Scheduled Tasks de Coolify: ese panel todavía no
# tiene dominio ni TLS, y usarlo implicaba mandar la contraseña en claro.
# Cuando lo tenga, esto puede mudarse allá y ganar visibilidad.
#
# El contenedor se busca por el label del dominio que sirve, no por su nombre:
# Coolify le pone un sufijo distinto en cada deploy, así que cualquier nombre
# fijo dura hasta la próxima subida. Se usa el label del dominio —que es
# público— y no el uuid interno de la aplicación, para no publicar
# identificadores de infraestructura en un repo abierto.
set -eu

DOMINIO_BACKEND=${ASTRA_API_DOMINIO:-https://api.astraguia.com}

contenedor=$(docker ps --filter "label=caddy_0=${DOMINIO_BACKEND}" --format '{{.Names}}' | head -1)
if [ -z "$contenedor" ]; then
    # Durante un deploy no hay backend arriba. No es un error: en dos minutos
    # vuelve a intentarlo.
    echo "sin contenedor de backend arriba, se saltea esta corrida"
    exit 0
fi

exec docker exec "$contenedor" python manage.py reanudar_informes

# Instalación (una vez, como root en el VPS):
#
#   install -m 755 reanudar-informes-cron.sh /usr/local/bin/reanudar-informes
#   ( crontab -l 2>/dev/null; echo '*/2 * * * * /usr/bin/flock -n /run/reanudar-informes.lock /usr/local/bin/reanudar-informes 2>&1 | /usr/bin/logger -t reanudar-informes' ) | crontab -
#
# `flock -n` evita que dos corridas se pisen: un informe tarda ~4 minutos y el
# cron dispara cada 2, así que sin esto habría dos procesos a la vez. El lock
# de generación ya impide que toquen el MISMO informe, pero no que se apilen.
#
# La salida va a syslog (`logger`), no a un archivo suelto: se rota sola.
# Para leerla:  journalctl -t reanudar-informes --since '1 hour ago'
