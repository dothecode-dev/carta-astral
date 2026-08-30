from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    Account,
    BirthData,
    Chart,
    CreditTransaction,
    Device,
    Interpretation,
    InterpretationSection,
    ProviderIdentity,
    Session,
    SubTombstone,
)

# De hoja a raíz: los FK a Account son SET_NULL (Chart, Interpretation,
# CreditTransaction, Device), no CASCADE, así que borrar la cuenta primero no
# se lleva puesto lo demás y hay que nombrar cada modelo.
#
# BirthData y Device no son de los siete modelos del RF16 (Account, Chart,
# Interpretation, InterpretationSection, CreditTransaction, ProviderIdentity,
# SubTombstone), pero los dos quedan huérfanos con datos de usuario si no se
# nombran:
# - BirthData guarda el mismo dato personal que Chart —nombre, fecha y
#   coordenadas de nacimiento— y queda huérfana en cuanto se borran las
#   cartas (el FK va de Chart a BirthData, no al revés). `api.deletion.
#   delete_charts` ya la trata como parte del borrado de una cuenta
#   individual.
# - Device cuelga de Account con SET_NULL: sin borrado explícito, sobrevive
#   a la purga con account_id=NULL y su platform/push_token intactos. Hoy no
#   la usa ningún código (tabla vacía en producción), pero el día que se
#   cablee push o telemetría sin acordarse de este comando, "purga total"
#   dejaría de serlo en silencio.
# Dejarlos afuera sería un olvido, no una decisión.
#
# Session SÍ es CASCADE (a diferencia de los seis de arriba): borrar Account
# se la lleva puesta igual sin nombrarla acá (fix wave final / Minor de la
# revisión final). Se la nombra de todas formas, ANTES de Account en el
# orden de borrado, para que el conteo y el reporte de este comando no
# omitan un modelo con datos de sesión (token_hash) que el comando SÍ borra
# — "esto es lo que se borraría" tiene que decir la verdad completa, no sólo
# la parte que se borra por `.delete()` explícito.
MODELOS_A_BORRAR = (
    ("InterpretationSection", InterpretationSection),
    ("CreditTransaction", CreditTransaction),
    ("Interpretation", Interpretation),
    ("Chart", Chart),
    ("BirthData", BirthData),
    ("ProviderIdentity", ProviderIdentity),
    ("SubTombstone", SubTombstone),
    ("Device", Device),
    ("Session", Session),
    ("Account", Account),
)


class Command(BaseCommand):
    help = (
        "RF16: purga TODO el historial de producción antes de deployar el modelo de "
        "dos tiers (cuentas, identidades SSO, cartas, interpretaciones, ledger de "
        "créditos y tombstones). No toca el CMS ni los geonames. Sin "
        "--si-estoy-seguro no borra nada, sólo informa qué borraría."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--si-estoy-seguro",
            action="store_true",
            dest="confirmado",
            help="Confirma el borrado. Sin este flag el comando es un dry-run.",
        )

    def handle(self, *args, **options):
        conteos = {nombre: modelo.objects.count() for nombre, modelo in MODELOS_A_BORRAR}

        if not options["confirmado"]:
            self.stdout.write("Sin --si-estoy-seguro no se borró nada. Esto es lo que se borraría:")
            for nombre, n in conteos.items():
                self.stdout.write(f"  {nombre}: {n}")
            return

        with transaction.atomic():
            for _, modelo in MODELOS_A_BORRAR:
                modelo.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Purga completa. Se borró:"))
        for nombre, n in conteos.items():
            self.stdout.write(f"  {nombre}: {n}")
