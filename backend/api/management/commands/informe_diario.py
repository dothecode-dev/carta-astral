"""Manda el informe diario de actividad.

Lo dispara una Scheduled Task de Coolify, como `reanudar_informes`. Se puede
correr a mano para ver qué saldría:

    python manage.py informe_diario           # junta, interpreta y manda
    python manage.py informe_diario --seco    # lo mismo, sin mandar el mail
"""

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
            datos = {}
            fallas = []
            for nombre, clave, fn in (
                ("PostHog", "sitio", informe_actividad.actividad_del_sitio),
                ("Search Console", "busquedas", informe_actividad.busquedas),
            ):
                try:
                    datos[clave] = fn()
                except Exception as exc:  # noqa: BLE001 — es una vista previa
                    fallas.append(f"{nombre}: {exc}")
            self.stdout.write(informe_actividad.redactar(datos))
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
