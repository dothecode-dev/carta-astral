"""Deploy 3 de la parte 2 de Vínculo: `chart` sale del estado de Django.

Las columnas y el `unique_together` viejo quedan en la base: el contenedor del
deploy 2 sigue atendiendo mientras esto corre y escribe `chart_id` en cada
INSERT. Las borra de verdad el primer deploy de la parte 3 (0050), cuando el
contenedor viejo ya no las conoce.

Lo que SÍ se va de la base son las tres FKs (`db_constraint=False`). El
`SET_NULL` de `Movimiento.chart` y `PasarelaCheckout.chart` lo hace Django, no
la base: con el campo fuera del estado nadie pone ese NULL, y la FK rechazaría
borrar cualquier carta con consumos o checkouts viejos —el borrado de cuenta,
la purga de compras anónimas vencidas—. Sin la restricción, esas filas quedan
con un `chart_id` que ya no apunta a nada, en una columna que nadie lee y que
la 0050 borra."""

from django.db import migrations, models
from django.db.models import deletion


class Migration(migrations.Migration):
    dependencies = [("api", "0048_contraer_sujeto")]

    operations = [
        migrations.AlterField(
            model_name="interpretation",
            name="chart",
            field=models.ForeignKey(
                "api.Chart", on_delete=deletion.CASCADE, null=True, blank=True,
                related_name="interpretations", db_constraint=False,
            ),
        ),
        migrations.AlterField(
            model_name="movimiento",
            name="chart",
            field=models.ForeignKey(
                "api.Chart", on_delete=deletion.SET_NULL, null=True, blank=True,
                related_name="movimientos", db_constraint=False,
            ),
        ),
        migrations.AlterField(
            model_name="pasarelacheckout",
            name="chart",
            field=models.ForeignKey(
                "api.Chart", on_delete=deletion.SET_NULL, null=True, blank=True,
                related_name="checkouts", db_constraint=False,
            ),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(name="interpretation", unique_together=set()),
                migrations.RemoveField(model_name="movimiento", name="chart"),
                migrations.RemoveField(model_name="pasarelacheckout", name="chart"),
                migrations.RemoveField(model_name="interpretation", name="chart"),
            ],
            database_operations=[],
        ),
    ]
