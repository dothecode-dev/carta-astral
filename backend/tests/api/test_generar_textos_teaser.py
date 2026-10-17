"""El comando que redacta los borradores del teaser (sin llamar a la API real)."""

import json

import pytest
from django.core.management import call_command

from api.management.commands import generar_textos_teaser as cmd
from tests.api.llm_falso import ClienteFalso


@pytest.fixture
def cliente(monkeypatch):
    falso = ClienteFalso()
    monkeypatch.setattr(cmd, "_build_client", lambda: falso)
    return falso


def test_genera_las_72_claves_del_idioma(cliente, tmp_path):
    salida = tmp_path / "t.json"
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert list(datos) == ["es"]
    assert len(datos["es"]) == 6 * 12
    assert "Sun|Ari" in datos["es"] and "Mars|Pis" in datos["es"]
    assert len(cliente.llamadas) == 72


def test_no_pisa_otros_idiomas(cliente, tmp_path):
    salida = tmp_path / "t.json"
    salida.write_text(json.dumps({"en": {"Sun|Ari": "keep me"}}), encoding="utf-8")
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    datos = json.loads(salida.read_text(encoding="utf-8"))
    assert datos["en"] == {"Sun|Ari": "keep me"}
    assert len(datos["es"]) == 72


def test_traduce_desde_el_idioma_revisado(cliente, tmp_path):
    salida = tmp_path / "t.json"
    es = {f"{c}|{s}": f"texto revisado {c} {s}" for c in cmd.CUERPOS_TEASER for s in cmd.SIGNOS}
    salida.write_text(json.dumps({"es": es}), encoding="utf-8")
    call_command("generar_textos_teaser", "--lang", "en", "--desde", "es", "--salida", str(salida))
    assert cliente.llamadas[0]["messages"][0]["content"] == "texto revisado Sun Ari"
    assert len(json.loads(salida.read_text(encoding="utf-8"))["en"]) == 72
