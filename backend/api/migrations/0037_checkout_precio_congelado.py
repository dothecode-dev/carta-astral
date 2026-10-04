from django.db import migrations, models

# Los precios vigentes hasta hoy, escritos acá y no importados del catálogo:
# el catálogo va a cambiar, y esta migración tiene que completar las filas
# viejas con el precio al que se abrieron, no con el de quien la corra.
PRECIOS_HASTA_EL_04_10_2026 = {
    "lectura_breve": 0,
    "informe_natal": 2900,
    "pack_3_natal": 7900,
    "pack_5_natal": 12500,
}


def completar(apps, schema_editor):
    PasarelaCheckout = apps.get_model("api", "PasarelaCheckout")
    for codigo, precio in PRECIOS_HASTA_EL_04_10_2026.items():
        PasarelaCheckout.objects.filter(
            codigo_producto=codigo, precio_centavos__isnull=True,
        ).update(precio_centavos=precio)


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0036_quitar_un_codigo_vigente_por_direccion"),
    ]

    operations = [
        migrations.AddField(
            model_name="pasarelacheckout",
            name="precio_centavos",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(completar, migrations.RunPython.noop),
    ]
