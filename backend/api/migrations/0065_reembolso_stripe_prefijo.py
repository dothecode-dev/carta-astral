from django.db import migrations
from django.db.models import Q


def prefijar(apps, schema_editor):
    """Los `Reembolso` de Stripe guardaban el id crudo (`re_…`, o `pyr_…` en
    los medios que Stripe reembolsa como «payment refund»); `cobro.reembolsar`
    usa `stripe:refund:<id>` como constancia y como clave del ledger. Sin esto,
    la reentrega de un reembolso viejo no lo reconocería como aplicado."""
    Reembolso = apps.get_model("api", "Reembolso")
    crudos = Q(refund_id__startswith="re_") | Q(refund_id__startswith="pyr_")
    for reembolso in Reembolso.objects.filter(crudos):
        reembolso.refund_id = f"stripe:refund:{reembolso.refund_id}"
        reembolso.save(update_fields=["refund_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0064_pago_id"),
    ]

    operations = [
        migrations.RunPython(prefijar, migrations.RunPython.noop),
    ]
