"""`actualizar_geoip`: baja la base de MaxMind y la deja atómicamente en
`GEOIP_PATH`. Sin clave no hace nada; con fallo de red, no toca lo que había."""

import io
import tarfile

import httpx
import pytest
from django.core.management import CommandError, call_command

from api import geo
from api.management.commands import actualizar_geoip


def _targz(contenido: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo("GeoLite2-Country_20261013/GeoLite2-Country.mmdb")
        info.size = len(contenido)
        tar.addfile(info, io.BytesIO(contenido))
    return buf.getvalue()


@pytest.fixture
def destino(tmp_path, settings):
    settings.GEOIP_PATH = str(tmp_path / "GeoLite2-Country.mmdb")
    settings.MAXMIND_ACCOUNT_ID = "123"
    settings.MAXMIND_LICENSE_KEY = "clave"
    return tmp_path / "GeoLite2-Country.mmdb"


def test_baja_descomprime_y_recarga(destino, monkeypatch):
    pedidos = []

    def get(url, auth=None, timeout=None, follow_redirects=False):
        pedidos.append((url, auth))
        return httpx.Response(200, content=_targz(b"MMDB"), request=httpx.Request("GET", url))

    monkeypatch.setattr(actualizar_geoip.httpx, "get", get)
    recargas = []
    monkeypatch.setattr(geo, "recargar", lambda: recargas.append(1))

    call_command("actualizar_geoip")

    assert destino.read_bytes() == b"MMDB"
    assert pedidos[0][1] == ("123", "clave")
    assert "GeoLite2-Country" in pedidos[0][0]
    assert recargas == [1]


def test_sin_clave_no_llama_y_lo_dice(destino, settings, monkeypatch, capsys):
    settings.MAXMIND_LICENSE_KEY = ""
    monkeypatch.setattr(actualizar_geoip.httpx, "get", lambda *a, **k: pytest.fail("no debía llamar"))

    call_command("actualizar_geoip")

    assert "MAXMIND" in capsys.readouterr().out
    assert not destino.exists()


def test_un_fallo_de_red_deja_la_base_anterior(destino, monkeypatch):
    destino.write_bytes(b"VIEJA")

    def get(url, auth=None, timeout=None, follow_redirects=False):
        raise httpx.ConnectError("boom", request=httpx.Request("GET", url))

    monkeypatch.setattr(actualizar_geoip.httpx, "get", get)

    with pytest.raises(CommandError):
        call_command("actualizar_geoip")

    assert destino.read_bytes() == b"VIEJA"
