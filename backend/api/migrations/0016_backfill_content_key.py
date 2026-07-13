"""Backfill de content_key para interpretaciones existentes, para que sirvan
de donantes en el dedup. Recalcula el hash desde chart.data con el
prompt_version de cada fila (no el actual)."""

import hashlib
import json

from django.db import migrations


def _content_key(chart_data, lang, prompt_version):
    canonical = json.dumps(chart_data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(f"{prompt_version}:{lang}:{canonical}".encode()).hexdigest()


def backfill(apps, schema_editor):
    Interpretation = apps.get_model("api", "Interpretation")
    batch = []
    for interp in Interpretation.objects.select_related("chart").filter(content_key="").iterator():
        interp.content_key = _content_key(interp.chart.data, interp.lang, interp.prompt_version)
        batch.append(interp)
        if len(batch) >= 500:
            Interpretation.objects.bulk_update(batch, ["content_key"])
            batch = []
    if batch:
        Interpretation.objects.bulk_update(batch, ["content_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0015_interpretation_content_key"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
