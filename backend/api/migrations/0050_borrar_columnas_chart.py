"""Parte 2 de Vínculo, tercer paso del esquema: el DROP real de `chart_id`.

La 0049 sacó `chart` del estado y borró sus FKs; las columnas quedaron porque
el contenedor del deploy 2 las seguía escribiendo. Acá ya convive el deploy 3,
que no las conoce. El estado no cambia: para que el `RemoveField` sepa qué
borrar —en SQLite reconstruye la tabla, en Postgres es un DROP COLUMN— se le
devuelve el campo SÓLO al estado interno de las operaciones de base."""

from django.db import migrations, models
from django.db.models import deletion


def _chart(related_name, on_delete):
    return models.ForeignKey(
        "api.Chart", on_delete=on_delete, null=True, blank=True,
        related_name=related_name, db_constraint=False,
    )


class Migration(migrations.Migration):
    dependencies = [("api", "0049_soltar_chart_del_estado")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.SeparateDatabaseAndState(
                    state_operations=[
                        migrations.AddField(
                            model_name="interpretation", name="chart",
                            field=_chart("interpretations", deletion.CASCADE),
                        ),
                        migrations.AlterUniqueTogether(
                            name="interpretation",
                            unique_together={("chart", "lang", "prompt_version", "tier")},
                        ),
                        migrations.AddField(
                            model_name="movimiento", name="chart",
                            field=_chart("movimientos", deletion.SET_NULL),
                        ),
                        migrations.AddField(
                            model_name="pasarelacheckout", name="chart",
                            field=_chart("checkouts", deletion.SET_NULL),
                        ),
                    ],
                ),
                migrations.AlterUniqueTogether(name="interpretation", unique_together=set()),
                migrations.RemoveField(model_name="interpretation", name="chart"),
                migrations.RemoveField(model_name="movimiento", name="chart"),
                migrations.RemoveField(model_name="pasarelacheckout", name="chart"),
            ],
            state_operations=[],
        ),
    ]
