"""Una variable JSON mal escrita no puede tumbar el proceso entero.

`STRIPE_PRECIOS` y `REVENUECAT_PRODUCT_CREDITS` se parsean al IMPORTAR
settings. Con `json.loads` a secas, una coma de más o unas comillas sobrantes
—lo más fácil de hacer pegando una variable en el panel de deploy— levantan
`JSONDecodeError` antes de que Django termine de arrancar: no falla el cobro,
falla el sitio entero, y el error aparece en el log de arranque de un
contenedor que se reinicia en loop.

El cobro sí tiene que quedar roto, y ruidosamente: sin mapeo, el checkout
responde 503 y el webhook descarta con "precio que no mapeamos". Eso se
arregla corrigiendo la variable; una API caída, no.
"""

from config.settings import _mapa_json


def test_un_json_valido_se_lee(monkeypatch):
    monkeypatch.setenv("UNA_VARIABLE", '{"price_x":"informe_natal"}')

    assert _mapa_json("UNA_VARIABLE") == {"price_x": "informe_natal"}


def test_una_variable_ausente_da_un_mapa_vacio(monkeypatch):
    monkeypatch.delenv("UNA_VARIABLE", raising=False)

    assert _mapa_json("UNA_VARIABLE") == {}


def test_un_json_roto_no_levanta_y_avisa(monkeypatch, capsys):
    """El caso real: pegar el valor con las comillas simples que necesita el
    `.env` local, donde el archivo se carga con `source`."""
    monkeypatch.setenv("UNA_VARIABLE", "'{\"price_x\":\"informe_natal\"}'")

    assert _mapa_json("UNA_VARIABLE") == {}
    assert "UNA_VARIABLE" in capsys.readouterr().err


def test_un_json_que_no_es_un_mapa_tampoco_pasa(monkeypatch, capsys):
    """`[1,2]` es JSON válido y rompería más tarde, al iterar el mapeo."""
    monkeypatch.setenv("UNA_VARIABLE", "[1, 2]")

    assert _mapa_json("UNA_VARIABLE") == {}
    assert "UNA_VARIABLE" in capsys.readouterr().err
