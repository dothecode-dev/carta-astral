"""Una constancia `Reembolso` por cada reembolso aplicado antes de que el
modelo existiera, a partir del `Movimiento` que dejó (`stripe:refund:<id>`).

Así la idempotencia del webhook tiene una sola fuente. El Movimiento no guarda
la compra ni el monto: quedan vacíos, y el monto ya está sumado en
`reembolsado_centavos` de su compra. Combos devueltos a medias, que no dejaban
Movimiento, no existieron nunca (ningún combo en el catálogo al 18-10-2026).
"""

from django.db import migrations

PREFIJO = "stripe:refund:"


def completar(apps, schema_editor):
    Movimiento = apps.get_model("api", "Movimiento")
    Reembolso = apps.get_model("api", "Reembolso")
    ids = (
        Movimiento.objects.filter(external_id__startswith=PREFIJO)
        .values_list("external_id", flat=True).distinct()
    )
    Reembolso.objects.bulk_create(
        [Reembolso(refund_id=e[len(PREFIJO):], monto=0) for e in ids if e[len(PREFIJO):]],
        ignore_conflicts=True,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0058_reembolso_registro"),
    ]

    operations = [
        migrations.RunPython(completar, migrations.RunPython.noop),
    ]
