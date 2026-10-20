"""Junta en «Argentina» los lugares que se guardaron con el nombre viejo de una
zona argentina (America/Cordoba → «Cordoba», …) antes de que `lugar_de_zona`
los reconociera (20-10-2026). Suma por día; no se pierde ninguna cuenta."""

from django.db import migrations
from django.db.models import F

# Copia fija de `conteo.LUGARES_VIEJOS_DE_ARGENTINA`: una migración no importa
# código que puede cambiar.
VIEJOS = ("Catamarca", "ComodRivadavia", "Cordoba", "Jujuy", "Mendoza", "Rosario")


def juntar(apps, schema_editor):
    ConteoProcedencia = apps.get_model("api", "ConteoProcedencia")
    for fila in ConteoProcedencia.objects.filter(tipo="lugar", valor__in=VIEJOS):
        destino, _ = ConteoProcedencia.objects.get_or_create(
            fecha=fila.fecha, tipo="lugar", valor="Argentina", defaults={"cantidad": 0},
        )
        # F(): el contenedor viejo sigue sumando a esta fila durante el deploy.
        ConteoProcedencia.objects.filter(pk=destino.pk).update(cantidad=F("cantidad") + fila.cantidad)
        fila.delete()


class Migration(migrations.Migration):
    dependencies = [("api", "0067_conteo_visitas_y_pais")]

    operations = [migrations.RunPython(juntar, migrations.RunPython.noop)]
