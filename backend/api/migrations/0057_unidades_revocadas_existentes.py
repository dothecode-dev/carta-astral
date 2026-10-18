"""Completa `unidades_revocadas` en las compras que ya tenían reembolsos.

Se deduce del monto devuelto con el mismo redondeo que usaba el webhook. Con
un solo reembolso por compra es exacto; con varios parciales puede quedar por
debajo de lo que de verdad se revocó, que es justo el error que el campo nuevo
evita de acá en adelante.
"""

from django.db import migrations


# Congelado del catálogo al 18-10-2026: una migración de datos no puede
# depender del catálogo vigente el día que corra. Unidades que otorga cada
# producto; ningún combo existe a esta fecha.
UNIDADES = {"lectura_breve": 1, "informe_natal": 1, "pack_3_natal": 3, "pack_5_natal": 5, "informe_vinculo": 1}


def completar(apps, schema_editor):
    PasarelaCheckout = apps.get_model("api", "PasarelaCheckout")
    for fila in PasarelaCheckout.objects.filter(reembolsado_centavos__gt=0):
        total = UNIDADES.get(fila.codigo_producto)
        if total is None or fila.precio_centavos is None:
            # La 0037 completó `precio_centavos` en todas las filas viejas.
            continue
        pagado = fila.precio_centavos - fila.descuento_centavos
        if pagado <= 0 or fila.reembolsado_centavos >= pagado:
            unidades = total
        else:
            unidades = min(total, -(-fila.reembolsado_centavos * total // pagado))
        PasarelaCheckout.objects.filter(pk=fila.pk).update(unidades_revocadas=unidades)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0056_disputa_registro"),
    ]

    operations = [
        migrations.RunPython(completar, migrations.RunPython.noop),
    ]
