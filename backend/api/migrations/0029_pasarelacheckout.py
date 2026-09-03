"""`PolarCheckout` → `PasarelaCheckout`, conservando las filas.

Escrita a mano a propósito. `makemigrations` no puede saber que es un renombre
—corre no interactivo en este repo— y generó `CreateModel` + `DeleteModel`, que
borra la tabla con todo adentro. Hay compras reales hechas con Polar y un
reembolso puede llegar meses después: `RenameModel` renombra la tabla y las
filas siguen ahí.

Ojo al desplegar: mientras el contenedor viejo siga vivo, su código busca
`api_polarcheckout`, que ya no existe. Por eso esto va con `make deploy`, que
pone el cartel de mantenimiento antes del swap.
"""

from django.db import migrations, models


def marcar_las_viejas_como_polar(apps, schema_editor):
    """Todo lo que ya existía se pagó con Polar.

    El campo nace con default `"stripe"`, así que sin esto las compras del
    02-09-2026 quedarían marcadas como de una pasarela que no las conoce: su
    reembolso se buscaría contra la API de Stripe y no aparecería.
    """
    apps.get_model("api", "PasarelaCheckout").objects.update(pasarela="polar")


class Migration(migrations.Migration):

    dependencies = [("api", "0028_polarcheckout_acreditado_at")]

    operations = [
        migrations.RenameModel(old_name="PolarCheckout", new_name="PasarelaCheckout"),
        migrations.AddField(
            model_name="pasarelacheckout",
            name="payment_intent",
            field=models.CharField(blank=True, default="", max_length=100),
        ),
        migrations.AddField(
            model_name="pasarelacheckout",
            name="pasarela",
            field=models.CharField(default="stripe", max_length=20),
        ),
        migrations.RunPython(marcar_las_viejas_como_polar, migrations.RunPython.noop),
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
