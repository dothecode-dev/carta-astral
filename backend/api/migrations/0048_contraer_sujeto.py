"""El informe pago cuelga sólo del sujeto. Parte 2 de Vínculo, deploy 2.

La 0047 ya dejó toda fila con su sujeto. `chart` queda NULL-able: el deploy 3
deja de escribirla, y la columna se borra en el primer deploy de la parte 3,
cuando ya no quede código que la conozca."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0047_rellenar_sujetos_de_nuevo")]

    operations = [
        migrations.AlterField(
            model_name="interpretation",
            name="sujeto",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="interpretations",
                to="api.sujeto",
            ),
        ),
        migrations.AlterField(
            model_name="interpretation",
            name="chart",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="interpretations",
                to="api.chart",
            ),
        ),
    ]
