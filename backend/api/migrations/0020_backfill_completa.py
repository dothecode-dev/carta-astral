"""Backfill de `completa` para interpretaciones que ya existían antes de la
Tarea 10.

El flujo viejo de interpretación armaba el texto completo en
un solo paso y no persistía `InterpretationSection` — ese modelo no existía
todavía. `0019` agrega `completa` con `default=False`: sin este backfill,
toda esa fila queda marcada como "en curso" apenas se aplica la migración.

Consecuencia si no se corre (trazada en revisión, no hipotética):
`interpretation_langs`/`_chart_repr` dejan de listar esas lecturas como
disponibles (el bug exacto que la Tarea 10 debía cerrar, reproducido para
el 100% de lo que ya existe), y un reintento del usuario hace que
`iniciar_generacion` encuentre la fila (no cobra de nuevo) pero
`completar_generacion` la trate como generación real: regenera las ocho
secciones desde cero para pisar un texto que ya estaba, y si esa
regeneración falla antes de persistir una sección, borra la interpretación
original y le acredita a la cuenta un crédito que nunca se cobró en ese
intento.

Marcador de "viene del flujo viejo": `text` no vacío y cero
`InterpretationSection`. Una fila de la Tarea 10 a medio generar tiene
`completa=False` Y `text=""` siempre — `generar_informe` sólo escribe
`text` en el mismo `save()` atómico que pone `completa=True` (ver
`api/informe_service.py::generar_informe`) — así que nunca matchea este
filtro: no hay forma de que esto marque como completa una generación real
en curso.

Idempotente: una segunda corrida no encuentra filas que sigan en
`completa=False` con esas condiciones (la primera ya las puso en `True`),
así que no hace nada.
"""

from django.db import migrations


def backfill(apps, schema_editor):
    Interpretation = apps.get_model("api", "Interpretation")
    (
        Interpretation.objects
        .filter(completa=False, secciones__isnull=True)
        .exclude(text="")
        .update(completa=True)
    )


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0019_interpretation_completa_interpretationsection"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
