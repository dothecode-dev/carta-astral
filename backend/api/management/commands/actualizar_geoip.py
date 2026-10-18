"""Baja la base GeoLite2-Country de MaxMind y la deja en `GEOIP_PATH`.

Corre en el arranque (`entrypoint.sh`) y en un Scheduled Task semanal de
Coolify («Actualizar GeoLite2», `0 5 * * 1`): la EULA de MaxMind exige
destruir las versiones viejas a los 30 días de una nueva. Sin cuenta o sin
clave no hace nada y lo dice; con un fallo de red deja la base anterior y
sale con error, que en el entrypoint se ignora (`|| true`).

    python manage.py actualizar_geoip
"""

import io
import os
import tarfile
import tempfile

import httpx
import maxminddb
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api import geo

_URL = "https://download.maxmind.com/geoip/databases/GeoLite2-Country/download?suffix=tar.gz"
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


class Command(BaseCommand):
    help = "Baja la base GeoLite2-Country a GEOIP_PATH."

    def handle(self, *args, **options):
        if not settings.MAXMIND_ACCOUNT_ID or not settings.MAXMIND_LICENSE_KEY:
            self.stdout.write("sin MAXMIND_ACCOUNT_ID / MAXMIND_LICENSE_KEY: no se baja la base")
            return
        destino = settings.GEOIP_PATH
        try:
            respuesta = httpx.get(
                _URL, auth=(settings.MAXMIND_ACCOUNT_ID, settings.MAXMIND_LICENSE_KEY),
                timeout=_TIMEOUT, follow_redirects=True,
            )
            respuesta.raise_for_status()
        except httpx.HTTPError as exc:
            # Sin el mensaje de httpx: trae la URL (sin clave acá, pero igual).
            raise CommandError(f"MaxMind no contestó: {type(exc).__name__}") from None

        mmdb = _extraer_mmdb(respuesta.content)
        carpeta = os.path.dirname(destino) or "."
        os.makedirs(carpeta, exist_ok=True)
        fd, temporal = tempfile.mkstemp(dir=carpeta, suffix=".mmdb.part")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(mmdb)
            try:
                maxminddb.open_database(temporal).close()
            except (maxminddb.InvalidDatabaseError, OSError, ValueError):
                raise CommandError(
                    "MaxMind devolvió un .mmdb inválido: se conserva la base anterior"
                ) from None
            os.replace(temporal, destino)  # atómico: nadie lee una base a medias
        finally:
            if os.path.exists(temporal):
                os.unlink(temporal)
        geo.recargar()
        self.stdout.write(f"base GeoLite2 actualizada en {destino} ({len(mmdb)} bytes)")


def _extraer_mmdb(targz: bytes) -> bytes:
    try:
        with tarfile.open(fileobj=io.BytesIO(targz), mode="r:gz") as tar:
            for miembro in tar.getmembers():
                if miembro.name.endswith(".mmdb"):
                    archivo = tar.extractfile(miembro)
                    if archivo is not None:
                        return archivo.read()
    except (tarfile.TarError, EOFError, OSError):
        raise CommandError("la respuesta de MaxMind no es un tar.gz") from None
    raise CommandError("el tar.gz de MaxMind no trae ningún .mmdb")
