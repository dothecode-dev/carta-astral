"""Completa `unidades_revocadas` en las compras que ya tenían reembolsos.

Se deduce del monto devuelto con el mismo redondeo que usaba el webhook. Con
un solo reembolso por compra es exacto; con varios parciales puede quedar por
debajo de lo que de verdad se revocó, que es justo el error que el campo nuevo
evita de acá en adelante. Un combo devuelto a medias no se revocaba: queda 0.
"""

from django.db import migrations


def completar(apps, schema_editor):
    from api import catalogo

    PasarelaCheckout = apps.get_model("api", "PasarelaCheckout")
    for fila in PasarelaCheckout.objects.filter(reembolsado_centavos__gt=0):
        prod = catalogo.CATALOGO.get(fila.codigo_producto)
        if prod is None:
            continue
        total = prod.otorga[0][1] if len(prod.otorga) == 1 else 1
        precio = fila.precio_centavos if fila.precio_centavos is not None else prod.precios.get(fila.moneda, 0)
        pagado = precio - fila.descuento_centavos
        if pagado <= 0 or fila.reembolsado_centavos >= pagado:
            unidades = total
        elif len(prod.otorga) != 1:
            unidades = 0
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
