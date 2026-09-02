"""Prende y apaga el modo mantenimiento. Lo usa `make deploy`.

    python manage.py mantenimiento on|off|estado

`estado` imprime el flag y cuántos informes se están escribiendo: es lo que
mira el drenaje antes de dejar pushear.
"""

import json

from django.core.management.base import BaseCommand

from api import mantenimiento


class Command(BaseCommand):
    help = "Prende (on), apaga (off) o consulta (estado) el modo mantenimiento."

    def add_arguments(self, parser):
        parser.add_argument("accion", choices=["on", "off", "estado"])

    def handle(self, *args, **options):
        accion = options["accion"]
        if accion == "on":
            mantenimiento.activar()
        elif accion == "off":
            mantenimiento.desactivar()

        # JSON siempre, incluso al prender y apagar: `make deploy` lee esta
        # salida por SSH y una frase en prosa lo obligaría a parsear texto.
        self.stdout.write(json.dumps({
            "mantenimiento": mantenimiento.activo(),
            "generando": mantenimiento.generando(),
        }))
