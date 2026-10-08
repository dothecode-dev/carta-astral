"""Juez + reparación del trato (interpret/revision_trato.py).

Medido en staging el 08-10: un informe neutro salió con «podés generar vos
misma el sacudón» pese a la instrucción. Cada sección pasa por un juez que
lista los fragmentos con el género equivocado y, si hay, por una reparación
acotada que se verifica antes de aceptarla. La revisión nunca hace fallar un
informe: ante cualquier duda devuelve el texto original.
"""

import json
import logging

import anthropic
import httpx
import pytest

from interpret import revision_trato
from interpret.prompts import MODEL
from interpret.revision_trato import revisar_trato
from interpret.trato import instruccion

TEXTO = (
    "## Tu motor\n\n"
    "Marte en Aries te da un empuje que no espera permiso. Cuando algo se "
    "estanca, podés generar vos misma el sacudón que hace falta, y eso te "
    "vuelve una persona capaz de abrir caminos donde otros ven paredes. La "
    "Luna en Cáncer, en cambio, es tranquila y protectora con lo propio.\n\n"
    "## Tu forma de pensar\n\n"
    "Mercurio en Géminis te lleva a saltar de un tema a otro con curiosidad, "
    "sin convertirte en especialista de una sola cosa. Leés, preguntás, "
    "conectás ideas que nadie había juntado, y en esa mezcla aparece lo más "
    "tuyo: la capacidad de traducir lo complejo en algo que se entiende. "
    "Trabajar así no tiene por qué ser una pelea constante contra vos."
)
FRAG = "generar vos misma el sacudón"
FRAG_OK = "generar por tu cuenta el sacudón"
REPARADO = TEXTO.replace(FRAG, FRAG_OK)


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = None


class _StreamCtx:
    def __init__(self, resultado):
        self._resultado = resultado

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if isinstance(self._resultado, BaseException):
            raise self._resultado
        return self._resultado


class ClienteFalso:
    """Devuelve las respuestas en orden (texto o excepción) y registra los
    kwargs de cada `messages.stream(...)`: la interfaz real que usa
    `generator._stream_text`."""

    def __init__(self, *respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.llamadas.append(kwargs)
            r = self.outer._respuestas.pop(0)
            return _StreamCtx(r if isinstance(r, (BaseException, _Resp)) else _Resp(r))

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def _juez(*fragmentos):
    return json.dumps({"fragmentos": list(fragmentos)}, ensure_ascii=False)


def _reemplazos(*pares):
    return json.dumps(
        {"reemplazos": [{"original": o, "corregido": c} for o, c in pares]}, ensure_ascii=False
    )


def _system(llamada):
    return "\n".join(b["text"] for b in llamada["system"])


# --- cuándo no se llama a nada ---


@pytest.mark.parametrize("trato", ["femenino", "masculino", "neutro", ""])
def test_ingles_no_llama_al_modelo(trato):
    cliente = ClienteFalso()
    assert revisar_trato(TEXTO, trato, "en", cliente) == TEXTO
    assert cliente.llamadas == []


def test_juez_sin_fragmentos_no_repara():
    cliente = ClienteFalso(_juez())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1


# --- el camino feliz ---


def test_reemplaza_el_fragmento_y_nada_mas(caplog):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == REPARADO
    # Fuera del fragmento, byte-idéntico.
    i = TEXTO.index(FRAG)
    assert resultado[:i] == TEXTO[:i]
    assert resultado[i + len(FRAG_OK):] == TEXTO[i + len(FRAG):]
    # Se loguean números, no texto.
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()]
    assert resumen and "listados=1" in resumen[0] and "aplicados=1" in resumen[0]
    assert "sacudón" not in resumen[0]


def test_la_reparacion_recibe_los_fragmentos_con_contexto_y_no_el_texto_entero():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)))
    revisar_trato(TEXTO, "neutro", "es", cliente)
    reparacion = cliente.llamadas[1]
    contenido = reparacion["messages"][0]["content"]
    assert FRAG in contenido
    assert "se estanca, podés" in contenido  # contexto de antes
    assert TEXTO not in contenido
    assert instruccion("neutro", "es") in _system(reparacion)
    formato = reparacion["output_config"]["format"]
    assert formato["type"] == "json_schema"
    assert formato["schema"]["required"] == ["reemplazos"]


def test_juez_con_bloque_json_tambien_se_entiende():
    cliente = ClienteFalso(f"```json\n{_juez(FRAG)}\n```", _reemplazos((FRAG, FRAG_OK)))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO


def test_fragmentos_que_no_estan_en_el_texto_se_descartan():
    """Un fragmento que el juez inventó no se le pide reparar a nadie."""
    cliente = ClienteFalso(_juez("esto no está en el texto"))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_las_dos_llamadas_van_sin_razonamiento_y_con_el_modelo_de_generacion(lang):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG_OK)))
    revisar_trato(TEXTO, "femenino", lang, cliente)
    assert len(cliente.llamadas) == 2
    for llamada in cliente.llamadas:
        assert llamada["model"] == MODEL
        assert llamada["thinking"] == {"type": "disabled"}


def test_el_juez_pide_salida_estructurada_con_techo_chico():
    cliente = ClienteFalso(_juez())
    revisar_trato(TEXTO, "neutro", "es", cliente)
    juez = cliente.llamadas[0]
    assert juez["max_tokens"] == 1000
    formato = juez["output_config"]["format"]
    assert formato["type"] == "json_schema"
    assert formato["schema"]["required"] == ["fragmentos"]
    assert TEXTO in juez["messages"][0]["content"]


@pytest.mark.parametrize(
    ("trato", "esperado", "ausente"),
    [
        ("femenino", "femenino", "masculino"),
        ("masculino", "masculino", "femenino"),
        ("neutro", "neutro", None),
        ("", "neutro", None),
    ],
)
def test_el_system_del_juez_nombra_el_trato(trato, esperado, ausente):
    cliente = ClienteFalso(_juez())
    revisar_trato(TEXTO, trato, "es", cliente)
    system = _system(cliente.llamadas[0])
    assert revision_trato.describir_trato(trato) in system
    assert esperado in revision_trato.describir_trato(trato)
    if ausente:
        assert ausente not in revision_trato.describir_trato(trato)


# --- pares que se descartan (el resto se aplica igual) ---


def test_un_par_que_introduce_vos_mismo_se_rechaza_y_el_otro_se_aplica(caplog):
    """Medido en staging: la reparación pasó «contra vos» a «contra vos mismo»."""
    contra = "una pelea constante contra vos"
    cliente = ClienteFalso(
        _juez(FRAG, contra),
        _reemplazos((FRAG, FRAG_OK), (contra, "una pelea constante contra vos mismo")),
    )
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]
    assert "aplicados=1" in resumen and "forma_prohibida=1" in resumen


def test_un_par_cuyo_original_no_listo_el_juez_se_descarta(caplog):
    otro = "Mercurio en Géminis"
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((otro, "Mercurio en Cáncer"), (FRAG, FRAG_OK)))
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    resumen = [r.getMessage() for r in caplog.records if "listados=" in r.getMessage()][0]
    assert "no_listado=1" in resumen


def test_un_par_identico_se_descarta():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, FRAG)))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


def test_un_par_con_salto_de_linea_se_descarta():
    frag = "## Tu motor\n\nMarte en Aries"
    cliente = ClienteFalso(_juez(frag), _reemplazos((frag, "## Tu impulso\n\nMarte en Aries")))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


@pytest.mark.parametrize(
    ("trato", "corregido", "rechazado"),
    [
        ("neutro", "generar vos misma el sacudón con calma", True),
        ("neutro", "generar por tu cuenta el sacudón", False),
        ("neutro", "gerar você mesmo o sacudón", True),
        ("neutro", "generar lo mismo de siempre", True),
        ("femenino", "generar vos mismo el sacudón", True),
        ("femenino", "generar vos misma el sacudón ya", False),
        ("masculino", "generar vos misma el sacudón ya", True),
        ("masculino", "generar vos mismo el sacudón", False),
        ("femenino", "gerar você mesmo o sacudón", True),
        ("masculino", "gerar você mesma o sacudón", True),
    ],
)
def test_formas_prohibidas_segun_el_trato(trato, corregido, rechazado):
    cliente = ClienteFalso(_juez(FRAG), _reemplazos((FRAG, corregido)))
    resultado = revisar_trato(TEXTO, trato, "es", cliente)
    assert resultado == (TEXTO if rechazado else TEXTO.replace(FRAG, corregido))


def test_reparacion_sin_reemplazos_devuelve_el_original():
    cliente = ClienteFalso(_juez(FRAG), _reemplazos())
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO


# --- fallos del LLM o JSON roto: el original ---


@pytest.mark.parametrize(
    "respuesta",
    ["esto no es json", '{"otra_cosa": []}', '{"fragmentos": "no es lista"}', '{"fragmentos": [1, 2]}'],
)
def test_juez_con_respuesta_ilegible_devuelve_el_original_y_loguea(respuesta, caplog):
    cliente = ClienteFalso(respuesta)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1
    assert any(r.levelno == logging.WARNING for r in caplog.records)


@pytest.mark.parametrize(
    "respuesta",
    [
        "esto no es json",
        '{"reemplazos": "no es lista"}',
        '{"reemplazos": [{"original": "x"}]}',
        '{"reemplazos": [{"original": 1, "corregido": 2}]}',
        _Resp('{"reemplazos": [', stop_reason="max_tokens"),
    ],
)
def test_reparacion_ilegible_devuelve_el_original_y_loguea(respuesta, caplog):
    cliente = ClienteFalso(_juez(FRAG), respuesta)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_error_del_llm_en_el_juez_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_error_del_llm_en_la_reparacion_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(_juez(FRAG), error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)
