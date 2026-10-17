"""El comando que redacta los borradores del teaser (sin llamar a la API real)."""

import json

import pytest
from django.core.management import CommandError, call_command

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


def test_se_niega_a_pisar_un_idioma_ya_escrito(cliente, tmp_path):
    salida = tmp_path / "t.json"
    previo = {"es": {"Sun|Ari": "editado a mano"}}
    salida.write_text(json.dumps(previo), encoding="utf-8")
    with pytest.raises(CommandError, match="--forzar"):
        call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    assert cliente.llamadas == []
    assert json.loads(salida.read_text(encoding="utf-8")) == previo


def test_forzar_regenera_un_idioma_existente(cliente, tmp_path):
    salida = tmp_path / "t.json"
    salida.write_text(json.dumps({"es": {"Sun|Ari": "viejo"}}), encoding="utf-8")
    call_command("generar_textos_teaser", "--lang", "es", "--forzar", "--salida", str(salida))
    assert len(json.loads(salida.read_text(encoding="utf-8"))["es"]) == 72


@pytest.mark.parametrize(
    ("lang", "pedido", "ausente", "presente"),
    [
        ("es", "el Sol en Aries", "Write", "voseo"),
        ("en", "the Sun in Aries", "Arrancás", "English"),
        ("pt", "o Sol em Áries", "Arrancás", "você"),
    ],
)
def test_el_prompt_va_en_el_idioma_destino(cliente, tmp_path, lang, pedido, ausente, presente):
    call_command("generar_textos_teaser", "--lang", lang, "--salida", str(tmp_path / "t.json"))
    primera = cliente.llamadas[0]
    system = primera["system"][0]["text"]
    assert primera["messages"][0]["content"] == pedido
    assert presente in system
    assert ausente not in system
    if lang != "es":
        assert "vos misma" not in system and "Escribís" not in system
