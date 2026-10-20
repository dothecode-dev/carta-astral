from django.db import migrations, models
from django.db.models import F


def marcar_acreditadas(apps, schema_editor):
    """Toda fila de Stripe ya acreditada se da por arrancada, igual que la 0062
    hizo con las de Mercado Pago: ahora Stripe también pasa por `cobro`, que lee
    `informe_arrancado_at`, y una fila vieja con el campo nulo re-arrancaría el
    informe en una repetición de la notificación."""
    PasarelaCheckout = apps.get_model("api", "PasarelaCheckout")
    PasarelaCheckout.objects.filter(
        pasarela="stripe", acreditado_at__isnull=False, informe_arrancado_at__isnull=True,
    ).update(informe_arrancado_at=F("acreditado_at"))


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0063_solicitud_arrepentimiento'),
    ]

    operations = [
        migrations.RenameField(
            model_name='pasarelacheckout',
            old_name='payment_intent',
            new_name='pago_id',
        ),
        migrations.AlterField(
            model_name='pasarelacheckout',
            name='pasarela',
            field=models.CharField(choices=[('stripe', 'stripe'), ('mercadopago', 'mercadopago')], max_length=12),
        ),
        migrations.RunPython(marcar_acreditadas, migrations.RunPython.noop),
    ]
