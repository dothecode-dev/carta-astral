"""Manda el informe diario de actividad.

Lo dispara una Scheduled Task de Coolify, como `reanudar_informes`. Se puede
correr a mano para ver qué saldría:

    python manage.py informe_diario           # junta, interpreta y manda
    python manage.py informe_diario --seco    # lo mismo, sin mandar el mail
"""

import json

from django.core.management.base import BaseCommand

from api import informe_actividad


class Command(BaseCommand):
    help = "Junta la actividad del sitio, la interpreta y la manda por mail."

    def add_arguments(self, parser):
        parser.add_argument(
            "--seco",
            action="store_true",
            help="Muestra el informe en pantalla en vez de mandarlo.",
        )

    def handle(self, *args, **options):
        if options["seco"]:
            datos, fallas = informe_actividad.juntar_fuentes()
            self.stdout.write(informe_actividad.redactar(datos))
            # Los números crudos, que en el mail van abajo: son lo que hay que
            # mirar para saber si una fuente trajo algo o vino vacía.
            self.stdout.write("\n--- datos ---")
            self.stdout.write(json.dumps(datos, ensure_ascii=False, indent=1))
            for falla in fallas:
                self.stderr.write(falla)
            return

        resultado = informe_actividad.generar_y_enviar()
        for falla in resultado["fallas"]:
            self.stderr.write(f"fuente caída — {falla}")
        self.stdout.write(
            self.style.SUCCESS("informe enviado")
            if resultado["enviado"]
            else "informe NO enviado (sin RESEND_API_KEY o sin INFORME_DESTINO)",
        )
