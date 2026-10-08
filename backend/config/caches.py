"""La configuración de la caché, como función para poder testearla.

`MAX_ENTRIES` existe porque el default de `DatabaseCache` (300) hace que, al
llenarse, Django borre un tercio de las claves POR ORDEN DE NOMBRE: se podía
llevar el flag de mantenimiento, los locks o los throttles. Lo vencido lo
borra `purgar_codigos_acceso`, no la poda (spec 2026-10-08, RF21/RF22).
"""
from django.core.exceptions import ImproperlyConfigured

MAX_ENTRIES = 100_000


def armar(usar_db: bool, debug: bool) -> dict:
    if usar_db:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.db.DatabaseCache",
                "LOCATION": "django_cache",
                "OPTIONS": {"MAX_ENTRIES": MAX_ENTRIES},
            }
        }
    if not debug:
        # Fail-fast, no degradación silenciosa: con LocMem cada worker de
        # gunicorn tiene SU PROPIO contador y los muros de costo no limitan.
        raise ImproperlyConfigured(
            "En producción hace falta caché compartida: seteá USE_DB_CACHE=1 "
            "(y corré `manage.py createcachetable`). Con LocMem el cap de costo, "
            "el throttle y el lock de interpretación no limitan nada."
        )
    return {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
