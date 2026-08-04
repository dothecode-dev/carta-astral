"""Crea los `Locale` de contenido del CMS: es, en, pt.

Wagtail sólo crea el idioma por defecto al migrar. Esta migración de datos
garantiza que los tres existan en cualquier entorno donde el CMS se levante
(dev, tests, producción): el `entrypoint.sh` corre `migrate` en cada arranque,
así que tiene que ser idempotente.
"""
from django.db import migrations

CODIGOS = ["es", "en", "pt"]


def crear_locales(apps, schema_editor):
    Locale = apps.get_model("wagtailcore", "Locale")
    for codigo in CODIGOS:
        Locale.objects.get_or_create(language_code=codigo)


def eliminar_locales_creados(apps, schema_editor):
    # No se borran: otras páginas pueden depender de estos locales para
    # entonces, y Wagtail no permite borrar el locale por defecto.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("cms", "0001_initial"),
        ("wagtailcore", "0097_baselogentry_uuid_action_timestamp_indexes"),
    ]

    operations = [
        migrations.RunPython(crear_locales, eliminar_locales_creados),
    ]
