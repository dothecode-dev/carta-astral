"""Antes de contraer: rellenar de nuevo. Parte 2 de Vínculo, deploy 2.

Vuelve a rellenar —la función de la 0039, idempotente— lo que el
contenedor del deploy 1 pudo escribir sin sujeto durante su vida y durante la
ventana de este deploy; después suelta los consumos que el `devolver` anterior
a la parte 2 desvinculó sólo por carta (lo hacía `adoptar_huerfanas`, que se
va con este deploy). La 0048 hace obligatorio el sujeto.

Separada de la 0048 a propósito: en Postgres, un UPDATE sobre filas con FKs
diferidas deja eventos de trigger pendientes, y un ALTER TABLE de la misma
tabla en la misma transacción falla («pending trigger events»). Cada migración
corre en su propia transacción."""

import importlib

from django.db import migrations

rellenar_0039 = importlib.import_module("api.migrations.0039_rellenar_sujetos").rellenar


def soltar_consumos_desvinculados(apps, schema_editor):
    """Un consumo natal sin carta y con sujeto se daría por cobrado y
    regalaría el informe junto con el derecho devuelto. Sólo natales: un
    consumo de vínculo no tiene carta por diseño."""
    Movimiento = apps.get_model("api", "Movimiento")
    Movimiento.objects.filter(
        tipo="consumo", chart__isnull=True, sujeto__producto="natal",
    ).update(sujeto=None)


class Migration(migrations.Migration):
    dependencies = [("api", "0046_entrada_cache")]

    operations = [
        migrations.RunPython(rellenar_0039, migrations.RunPython.noop),
        migrations.RunPython(soltar_consumos_desvinculados, migrations.RunPython.noop),
    ]
