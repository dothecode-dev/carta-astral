"""Cada carta con su sujeto natal, y cada informe, consumo y checkout con el
de su carta. Parte 2 de Vínculo, deploy 1.

`rellenar` es idempotente y la vuelve a llamar la 0047 (deploy 2): entre las
dos, el contenedor viejo pudo escribir filas sin sujeto."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


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

    # Una sola sentencia por modelo. Si el contenedor viejo creó una carta
    # después del `bulk_create`, su subconsulta da NULL y la fila queda sin
    # sujeto: la 0047 vuelve a pasar. Con un dict en memoria eso era un `KeyError` que
    # abortaba la migración y tiraba el deploy.
    natal = Sujeto.objects.filter(natal_de_id=OuterRef("chart_id")).values("id")[:1]
    filas = 0
    for modelo in (Interpretation, Movimiento, PasarelaCheckout):
        filas += modelo.objects.filter(sujeto__isnull=True, chart__isnull=False).update(
            sujeto_id=Subquery(natal),
        )
    return {"sujetos": len(nuevos), "filas": filas}


class Migration(migrations.Migration):
    dependencies = [("api", "0038_sujeto")]

    operations = [migrations.RunPython(rellenar, migrations.RunPython.noop)]
