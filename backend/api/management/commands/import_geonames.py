"""Importa el dataset de GeoNames (cities500) a la DB local.

Idempotente: re-correrlo deja la tabla en el mismo estado (truncate + reload
dentro de una transacción). El dataset NO se versiona en git.

Uso normal (descarga): ``./manage.py import_geonames``
Tests / offline: ``./manage.py import_geonames --file cities.txt --admin1-file admin1.txt``
"""

import csv
import io
import json
import urllib.request
import zipfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api.models import GeoName, GeoNameToken
from api.text_norm import tokenize

GEONAMES_BASE = "https://download.geonames.org/export/dump/"
ADMIN1_FILE = "admin1CodesASCII.txt"
MIN_COLS = 18  # cities500 trae 19; el timezone está en la col 17
# Exónimos curados ES/EN/PT (exónimo normalizado -> geonameid). Ampliable;
# los geonameids deben validarse contra el dataset real (ver progress.md).
EXONYMS_PATH = Path(__file__).resolve().parents[2] / "data" / "exonyms.json"


class Command(BaseCommand):
    help = "Importa GeoNames (cities500) a la DB local (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default="cities500", help="nombre del dump de GeoNames")
        parser.add_argument("--file", default=None, help="TSV local de geonames (salta la descarga)")
        parser.add_argument("--admin1-file", default=None, help="admin1CodesASCII.txt local")

    def handle(self, *args, **opts):
        lines = self._read_geonames(opts)
        admin1 = self._read_admin1(opts)
        exonyms = self._read_exonyms()
        n_cities, n_tokens = self._load(lines, admin1, exonyms)
        self.stdout.write(self.style.SUCCESS(f"importadas {n_cities} ciudades, {n_tokens} tokens"))

    def _read_exonyms(self) -> dict[str, int]:
        if not EXONYMS_PATH.exists():
            return {}
        return json.loads(EXONYMS_PATH.read_text(encoding="utf-8"))

    # --- lectura de fuentes ---

    def _read_geonames(self, opts) -> list[str]:
        if opts["file"]:
            path = Path(opts["file"])
            if not path.exists():
                raise CommandError(f"archivo no encontrado: {path}")
            return path.read_text(encoding="utf-8").splitlines()
        url = f"{GEONAMES_BASE}{opts['dataset']}.zip"
        self.stdout.write(f"descargando {url} ...")
        try:
            with urllib.request.urlopen(url) as resp:  # noqa: S310 (URL fija de GeoNames)
                blob = resp.read()
        except OSError as exc:
            raise CommandError(f"no se pudo descargar {url}: {exc}") from exc
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            txt = zf.read(f"{opts['dataset']}.txt").decode("utf-8")
        return txt.splitlines()

    def _read_admin1(self, opts) -> dict[str, str]:
        path = opts["admin1_file"]
        if path:
            lines = Path(path).read_text(encoding="utf-8").splitlines()
        elif opts["file"]:
            return {}  # import local sin admin1 explícito: admin1 queda vacío
        else:
            url = f"{GEONAMES_BASE}{ADMIN1_FILE}"
            self.stdout.write(f"descargando {url} ...")
            try:
                with urllib.request.urlopen(url) as resp:  # noqa: S310
                    lines = resp.read().decode("utf-8").splitlines()
            except OSError as exc:
                raise CommandError(f"no se pudo descargar {url}: {exc}") from exc
        # formato: "AR.17\tRío Negro\tRio Negro\t<gid>"
        out: dict[str, str] = {}
        for line in lines:
            cols = line.split("\t")
            if len(cols) >= 2:
                out[cols[0]] = cols[1]
        return out

    # --- carga ---

    @transaction.atomic
    def _load(self, lines: list[str], admin1: dict[str, str], exonyms: dict[str, int]) -> tuple[int, int]:
        GeoNameToken.objects.all().delete()
        GeoName.objects.all().delete()

        cities: list[GeoName] = []
        for cols in csv.reader(lines, delimiter="\t"):
            if len(cols) < MIN_COLS:
                continue
            country, a1code = cols[8], cols[10]
            cities.append(
                GeoName(
                    geonameid=int(cols[0]),
                    name=cols[1],
                    asciiname=cols[2],
                    lat=float(cols[4]),
                    lng=float(cols[5]),
                    country_code=country,
                    admin1_code=a1code,
                    admin1=admin1.get(f"{country}.{a1code}", ""),
                    tz_geonames=cols[17],
                    population=int(cols[14] or 0),
                )
            )
        GeoName.objects.bulk_create(cities, batch_size=5000)

        tokens: list[GeoNameToken] = []
        for g in cities:  # bulk_create asignó los pk
            for tok in tokenize(g.name):
                tokens.append(GeoNameToken(geoname=g, token=tok))

        # Alias de exónimos: tokens extra apuntando a la ciudad de grafía local.
        # Se ignoran los exónimos cuyo geonameid no esté en el dataset cargado.
        by_gid = {g.geonameid: g for g in cities}
        for exonym, gid in exonyms.items():
            g = by_gid.get(gid)
            if g is None:
                continue
            for tok in tokenize(exonym):
                tokens.append(GeoNameToken(geoname=g, token=tok))

        GeoNameToken.objects.bulk_create(tokens, batch_size=5000)

        return len(cities), len(tokens)
