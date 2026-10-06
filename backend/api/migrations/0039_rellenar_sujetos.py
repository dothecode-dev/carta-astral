"""Cada carta con su sujeto natal, y cada informe, consumo y checkout con el
de su carta. Parte 2 de Vínculo, deploy 1.

`rellenar` es idempotente y la vuelve a llamar la 0040 (deploy 2): entre las
dos, el contenedor viejo pudo escribir filas sin sujeto (ver
`api.sujetos.adoptar_huerfanas`)."""

from django.db import migrations


def rellenar(apps, schema_editor=None) -> dict:
    Chart = apps.get_model("api", "Chart")
    Sujeto = apps.get_model("api", "Sujeto")
    Interpretation = apps.get_model("api", "Interpretation")
    Movimiento = apps.get_model("api", "Movimiento")
    PasarelaCheckout = apps.get_model("api", "PasarelaCheckout")

    con_sujeto = set(Sujeto.objects.filter(natal_de__isnull=False).values_list("natal_de_id", flat=True))
    nuevos = [
        Sujeto(producto="natal", natal_de_id=carta_id, account_id=account_id)
        for carta_id, account_id in Chart.objects.values_list("id", "account_id")
        if carta_id not in con_sujeto
    ]
    Sujeto.objects.bulk_create(nuevos, batch_size=500)

    por_carta = dict(Sujeto.objects.filter(natal_de__isnull=False).values_list("natal_de_id", "id"))
    filas = 0
    for modelo in (Interpretation, Movimiento, PasarelaCheckout):
        for pk, carta_id in modelo.objects.filter(
            sujeto__isnull=True, chart__isnull=False,
        ).values_list("pk", "chart_id"):
            filas += modelo.objects.filter(pk=pk).update(sujeto_id=por_carta[carta_id])
    return {"sujetos": len(nuevos), "filas": filas}


class Migration(migrations.Migration):
    dependencies = [("api", "0038_sujeto")]

    operations = [migrations.RunPython(rellenar, migrations.RunPython.noop)]
