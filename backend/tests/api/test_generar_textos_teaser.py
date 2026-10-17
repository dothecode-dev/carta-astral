"""El comando que redacta los borradores del teaser (sin llamar a la API real)."""

import json

import pytest
from django.core.management import CommandError, call_command

from api.management.commands import generar_textos_teaser as cmd
from tests.api.llm_falso import ClienteFalso


# 60 palabras sin muletillas ni formas con género: pasa la validación del comando.
LIMPIO = " ".join(f"palabra{i}" for i in range(60))


@pytest.fixture
def cliente(monkeypatch):
    falso = ClienteFalso(textos=lambda n: LIMPIO)
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


def _textos(frase: str, cuantos: int) -> dict[str, str]:
    return {f"k{i}": f"{frase} resto {i}" for i in range(cuantos)}


def test_frases_repetidas_detecta_una_frase_en_siete_textos_y_no_en_seis():
    assert ("tu identidad se", 7) in cmd.frases_repetidas(_textos("tu identidad se construye", 7))
    assert not any(f == "tu identidad se" for f, _ in cmd.frases_repetidas(_textos("tu identidad se construye", 6)))


def test_frases_repetidas_cuenta_textos_distintos_no_apariciones():
    textos = {"a": "tu identidad se " * 10, "b": "otra cosa distinta"}
    assert cmd.frases_repetidas(textos) == []


def test_frases_repetidas_ignora_ngramas_de_solo_palabras_vacias():
    textos = {f"k{i}": f"de la en {'xyz' * (i + 1)} pelo{i}" for i in range(10)}
    assert cmd.frases_repetidas(textos) == []


def test_frases_repetidas_ordena_por_frecuencia_descendente():
    textos = {f"k{i}": "luna brilla fuerte" + (" sol arde mucho" if i < 8 else "") for i in range(10)}
    res = cmd.frases_repetidas(textos)
    assert res[0] == ("luna brilla fuerte", 10)
    assert ("sol arde mucho", 8) in res


def test_muletillas_presentes_cuenta_por_texto_no_por_aparicion():
    textos = {"a": "Te cuesta mucho. Te cuesta otra vez.", "b": "a veces dudás", "c": "nada"}
    res = cmd.muletillas_presentes(textos, "es")
    assert res["te cuesta"] == 1
    assert res["a veces"] == 1
    assert "sin pedir permiso" not in res


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_prompt_de_generacion_es_y_pt_tiene_regla_de_genero_y_muletillas(lang):
    system = cmd._SISTEMA_GENERAR[lang]
    assert "neutr" in system.lower()
    assert any(m in system for m in cmd.MULETILLAS[lang])


def test_prompt_de_generacion_en_no_tiene_regla_de_genero():
    for system in (cmd._SISTEMA_GENERAR["en"], cmd._SISTEMA_TRADUCIR["en"]):
        assert "gender" not in system.lower()
    assert any(m in cmd._SISTEMA_GENERAR["en"] for m in cmd.MULETILLAS["en"])


@pytest.mark.parametrize("lang", ["en", "pt"])
def test_prompt_de_traduccion_lleva_las_prohibiciones(lang):
    system = cmd._SISTEMA_TRADUCIR[lang]
    assert any(m in system for m in cmd.MULETILLAS[lang])


def test_los_prompts_de_generacion_se_formatean_sin_llaves_sueltas():
    for lang, system in cmd._SISTEMA_GENERAR.items():
        assert "{" not in system.format(cuerpo="X", signo="Y")


def test_el_comando_avisa_por_stderr_de_repeticion_y_muletillas(cliente, tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cmd, "_stream_text", lambda *a, **k: "Siempre te cuesta mirar el cielo con calma.")
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(tmp_path / "t.json"))
    err = capsys.readouterr().err
    assert "REPETIDA en 72 textos: «te cuesta mirar»" in err
    assert "MULETILLA prohibida en 72 textos: «te cuesta»" in err


def test_muletillas_presentes_respeta_limite_de_palabra():
    textos = {"a": "Tenés elegancia natural y te cuestan los cambios."}
    assert cmd.muletillas_presentes(textos, "es") == {}


def test_aperturas_cuentan_solo_al_inicio_del_parrafo():
    textos = {
        "a": "«Con Venus en casa, buscás calma.»",
        "b": "Buscás calma. Con Venus en casa todo cambia.",
        "c": "Tenés el don de escuchar.",
    }
    assert cmd.muletillas_presentes(textos, "es") == {"con venus en": 1, "tenés el": 1}


@pytest.mark.parametrize("lang", ["es", "en", "pt"])
@pytest.mark.parametrize("tabla", ["_SISTEMA_GENERAR", "_SISTEMA_TRADUCIR"])
def test_ningun_ejemplo_del_prompt_usa_una_muletilla(lang, tabla):
    # Fuera de la lista de prohibidas (que las nombra a propósito), el resto del
    # prompt —ejemplos de tono y de reescritura— no puede modelar una muletilla.
    resto = getattr(cmd, tabla)[lang].replace(cmd._PROHIBIDAS[lang], "").lower()
    assert not [m for m in cmd.MULETILLAS[lang] if m in resto]


def test_el_prompt_de_traduccion_no_pide_variar_la_apertura():
    for lang in ("es", "en", "pt"):
        assert cmd._APERTURA_VARIADA[lang] not in cmd._SISTEMA_TRADUCIR[lang]
        assert cmd._APERTURA_VARIADA[lang] in cmd._SISTEMA_GENERAR[lang]


def _con_textos(monkeypatch, textos):
    falso = ClienteFalso(textos=textos)
    monkeypatch.setattr(cmd, "_build_client", lambda: falso)
    return falso


def _una_clave(monkeypatch):
    monkeypatch.setattr(cmd.Command, "_claves", staticmethod(lambda: ["Sun|Ari"]))


def test_reintenta_si_el_texto_trae_una_muletilla_y_guarda_el_limpio(monkeypatch, tmp_path):
    _una_clave(monkeypatch)
    sucio = "Siempre te cuesta mirar el cielo. " + LIMPIO
    falso = _con_textos(monkeypatch, lambda n: sucio if n == 1 else LIMPIO)
    salida = tmp_path / "t.json"
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    assert len(falso.llamadas) == 2
    assert json.loads(salida.read_text(encoding="utf-8"))["es"]["Sun|Ari"] == LIMPIO
    pedido = falso.llamadas[1]["messages"][0]["content"]
    assert pedido.startswith("el Sol en Aries") and "Evitá" in pedido and "te cuesta" in pedido


def test_siempre_sucio_hace_cuatro_llamadas_guarda_el_mejor_y_avisa(monkeypatch, tmp_path, capsys):
    _una_clave(monkeypatch)
    # Mejora en el 3er intento (1 problema contra 2); el resto es peor.
    dos = "te cuesta a veces " + LIMPIO
    uno = "te cuesta " + LIMPIO
    falso = _con_textos(monkeypatch, lambda n: uno if n == 3 else dos)
    salida = tmp_path / "t.json"
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    assert len(falso.llamadas) == 4
    assert json.loads(salida.read_text(encoding="utf-8"))["es"]["Sun|Ari"] == uno
    err = capsys.readouterr().err
    assert "Sun|Ari" in err and "te cuesta" in err and "1 textos con reintento" in err


def test_la_traduccion_tambien_reintenta(monkeypatch, tmp_path):
    _una_clave(monkeypatch)
    falso = _con_textos(monkeypatch, lambda n: "it's hard for you " + LIMPIO if n == 1 else LIMPIO)
    salida = tmp_path / "t.json"
    salida.write_text(json.dumps({"es": {"Sun|Ari": "original"}}), encoding="utf-8")
    call_command("generar_textos_teaser", "--lang", "en", "--desde", "es", "--salida", str(salida))
    assert len(falso.llamadas) == 2
    # El mensaje de usuario es exactamente el texto de origen; la lista va en el system.
    assert falso.llamadas[1]["messages"][0]["content"] == "original"
    assert falso.llamadas[0]["messages"][0]["content"] == "original"
    system = " ".join(b["text"] for b in falso.llamadas[1]["system"])
    assert "Avoid" in system and "it's hard for you" in system
    assert len(falso.llamadas[0]["system"]) == 1


def test_problemas_detecta_genero_en_es_y_pt_y_no_en_en():
    assert any("entero" in p for p in cmd.problemas_de_texto("Querés mostrarte entero. " + LIMPIO, "es"))
    assert any("atrapada" in p for p in cmd.problemas_de_texto("Sentís quedarte atrapada. " + LIMPIO, "es"))
    assert any("seguro de" in p for p in cmd.problemas_de_texto("Estás seguro de vos. " + LIMPIO, "es"))
    assert any("despercebido" in p for p in cmd.problemas_de_texto("Prefere passar despercebido. " + LIMPIO, "pt"))
    assert cmd.problemas_de_texto("Estás entero. " + LIMPIO, "en") == []


def test_problemas_genero_es_palabra_completa_y_sin_mayusculas():
    assert cmd.problemas_de_texto("Enteros ejemplos, enterovirus. " + LIMPIO, "es") == []
    assert cmd.problemas_de_texto("Te mostrás ENTERA " + LIMPIO, "es") != []


def test_solo_adverbio_no_es_marca_de_genero():
    # Decisión: «solo» queda fuera de FORMAS_CON_GENERO porque «no solo» / «solo cuando»
    # son adverbio y darían falsos positivos constantes; «sola» sí está.
    assert cmd.problemas_de_texto("No solo avanzás, solo cuando querés. " + LIMPIO, "es") == []
    assert cmd.problemas_de_texto("Te quedás sola. " + LIMPIO, "es") != []


def test_problemas_de_largo_y_texto_limpio():
    assert cmd.problemas_de_texto(LIMPIO, "es") == []
    assert any("largo" in p for p in cmd.problemas_de_texto("muy corto", "es"))
    assert any("largo" in p for p in cmd.problemas_de_texto(" ".join(["x"] * 111), "es"))


def test_problemas_incluye_muletillas_con_el_mismo_criterio():
    assert cmd.problemas_de_texto("Tenés elegancia y te cuestan cosas. " + LIMPIO, "es") == []
    assert cmd.problemas_de_texto("Con Venus en casa. " + LIMPIO, "es") != []
    assert cmd.problemas_de_texto(LIMPIO + " con Venus en casa", "es") == []


@pytest.mark.parametrize(
    ("lang", "frase"),
    [
        ("es", "Una energía intensa te acompaña."),
        ("es", "Recorrés el mundo entero."),
        ("es", "Pasa una sola vez."),
        ("pt", "Você aproveita a semana inteira."),
        ("pt", "O prazo ficou preso na agenda."),
    ],
)
def test_forma_con_genero_fuera_de_contexto_no_es_problema(lang, frase):
    assert cmd.problemas_de_texto(frase + " " + LIMPIO, lang) == []


@pytest.mark.parametrize(
    ("lang", "frase"),
    [
        ("es", "Preferís mostrarte entero."),
        ("es", "Evitás quedarte quieta."),
        ("es", "No querés pasar inadvertido."),
        ("es", "Odiás ser conquistado."),
        ("pt", "Você fica presa."),
    ],
)
def test_forma_con_genero_en_contexto_es_problema(lang, frase):
    assert any(p.startswith("género") for p in cmd.problemas_de_texto(frase + " " + LIMPIO, lang))


def test_el_mejor_intento_prefiere_largo_en_rango_aunque_tenga_muletilla(monkeypatch, tmp_path):
    _una_clave(monkeypatch)
    cortito = "palabra " * 5  # 1 solo problema (largo), pero fuera de rango
    con_muletilla = "te cuesta " + LIMPIO + " a veces"  # 2 problemas, largo en rango
    falso = _con_textos(monkeypatch, lambda n: cortito if n == 1 else con_muletilla)
    salida = tmp_path / "t.json"
    call_command("generar_textos_teaser", "--lang", "es", "--salida", str(salida))
    assert len(falso.llamadas) == 4
    assert json.loads(salida.read_text(encoding="utf-8"))["es"]["Sun|Ari"] == con_muletilla.strip()
