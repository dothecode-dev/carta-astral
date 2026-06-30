import uuid as uuid_lib

from django.db import migrations, models


def populate_uuids(apps, schema_editor):
    Chart = apps.get_model('api', 'Chart')
    for chart in Chart.objects.all():
        chart.uuid = uuid_lib.uuid4()
        chart.save(update_fields=['uuid'])


class Migration(migrations.Migration):
    dependencies = [('api', '0004_installation')]

    operations = [
        migrations.AddField(
            model_name='chart',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(populate_uuids, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='chart',
            name='uuid',
            field=models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True),
        ),
    ]
