"""`PolarCheckout` → `PasarelaCheckout`, conservando las filas.

Escrita a mano a propósito. `makemigrations` no puede saber que es un renombre
—corre no interactivo en este repo— y generó `CreateModel` + `DeleteModel`, que
borra la tabla con todo adentro. `RenameModel` la renombra y las filas siguen.

Ojo al desplegar: mientras el contenedor viejo siga vivo, su código busca
`api_polarcheckout`, que ya no existe. Por eso esto va con `make deploy`, que
pone el cartel de mantenimiento antes del swap.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("api", "0028_polarcheckout_acreditado_at")]

    operations = [
        migrations.RenameModel(old_name="PolarCheckout", new_name="PasarelaCheckout"),
        migrations.AddField(
            model_name="pasarelacheckout",
            name="payment_intent",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AlterField(
            model_name="pasarelacheckout",
            name="account",
            field=models.ForeignKey(
                null=True, on_delete=models.SET_NULL, related_name="checkouts",
                to="api.account",
            ),
        ),
        migrations.AlterField(
            model_name="pasarelacheckout",
            name="chart",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=models.SET_NULL,
                related_name="checkouts", to="api.chart",
            ),
        ),
    ]
