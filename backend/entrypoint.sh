#!/bin/sh
set -e

# Migraciones en cada arranque (idempotentes).
python manage.py migrate --noinput

# Tabla del DatabaseCache: el throttle, el tope global y el lock viven acá en prod.
# Idempotente; sólo tiene sentido con USE_DB_CACHE=1.
if [ -n "$USE_DB_CACHE" ]; then
    python manage.py createcachetable
fi

# NOTA: el dataset GeoNames NO se carga acá (trunca+recarga ~234k filas y tarda).
# Correr una sola vez, manualmente, post-deploy:  python manage.py import_geonames

exec gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout 60
