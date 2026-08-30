from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import (
    Account,
    BirthData,
    Chart,
    CreditTransaction,
    Interpretation,
    InterpretationSection,
    ProviderIdentity,
    SubTombstone,
)

# De hoja a raíz: los FK a Account son SET_NULL (Chart, Interpretation,
# CreditTransaction), no CASCADE, así que borrar la cuenta primero no se
# lleva puesto lo demás y hay que nombrar cada modelo.
#
# BirthData no es uno de los siete modelos del RF16 (Account, Chart,
# Interpretation, InterpretationSection, CreditTransaction, ProviderIdentity,
# SubTombstone), pero guarda el mismo dato personal que Chart —nombre, fecha
# y coordenadas de nacimiento— y queda huérfana en cuanto se borran las
# cartas (el FK va de Chart a BirthData, no al revés). `api.deletion.
# delete_charts` ya la trata como parte del borrado de una cuenta
# individual; dejarla afuera de la purga sería un olvido, no una decisión.
MODELOS_A_BORRAR = (
    ("InterpretationSection", InterpretationSection),
    ("CreditTransaction", CreditTransaction),
    ("Interpretation", Interpretation),
    ("Chart", Chart),
    ("BirthData", BirthData),
    ("ProviderIdentity", ProviderIdentity),
    ("SubTombstone", SubTombstone),
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
