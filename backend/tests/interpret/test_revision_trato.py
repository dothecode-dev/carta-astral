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
from interpret.prompts import MODEL, TRANSLATE_MAX_TOKENS_GENERACION
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
    "tuyo: la capacidad de traducir lo complejo en algo que se entiende."
)
REPARADO = TEXTO.replace("vos misma", "por tu cuenta")


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


def test_juez_con_fragmentos_repara_y_devuelve_lo_reparado(caplog):
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), REPARADO)
    with caplog.at_level(logging.INFO, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
    assert len(cliente.llamadas) == 2
    reparacion = cliente.llamadas[1]
    contenido = reparacion["messages"][0]["content"]
    assert "generar vos misma el sacudón" in contenido
    assert TEXTO in contenido
    assert instruccion("neutro", "es") in _system(reparacion)
    assert reparacion["max_tokens"] == TRANSLATE_MAX_TOKENS_GENERACION
    # Se loguea el número, no el texto.
    aceptada = [r for r in caplog.records if r.levelno == logging.INFO and "reparación" in r.getMessage()]
    assert aceptada and "fragmentos=1" in aceptada[0].getMessage()
    assert "sacudón" not in aceptada[0].getMessage()


def test_juez_con_bloque_json_tambien_se_entiende():
    cliente = ClienteFalso(f"```json\n{_juez('generar vos misma el sacudón')}\n```", REPARADO)
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO


def test_fragmentos_que_no_estan_en_el_texto_se_descartan():
    """Un fragmento que el juez inventó no se le pide reparar a nadie."""
    cliente = ClienteFalso(_juez("esto no está en el texto"))
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert len(cliente.llamadas) == 1


@pytest.mark.parametrize("lang", ["es", "pt"])
def test_las_dos_llamadas_van_sin_razonamiento_y_con_el_modelo_de_generacion(lang):
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), REPARADO)
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


# --- reparaciones que no se aceptan ---


def _reparacion_rechazada(reparado, caplog):
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), reparado)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        resultado = revisar_trato(TEXTO, "neutro", "es", cliente)
    assert resultado == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_reparacion_que_cambia_demasiado_devuelve_el_original(caplog):
    reescrito = TEXTO.replace(
        "Leés, preguntás, conectás ideas que nadie había juntado",
        "Tu mente funciona como una red que no para de tejer conexiones nuevas",
    ).replace("vos misma", "por tu cuenta")
    _reparacion_rechazada(reescrito, caplog)


def test_reparacion_que_toca_un_encabezado_devuelve_el_original(caplog):
    _reparacion_rechazada(REPARADO.replace("## Tu motor", "## Tu impulso"), caplog)


def test_reparacion_que_pierde_un_encabezado_devuelve_el_original(caplog):
    _reparacion_rechazada(REPARADO.replace("## Tu forma de pensar\n\n", ""), caplog)


def test_reparacion_vacia_devuelve_el_original(caplog):
    # `_stream_text` ya rechaza la respuesta vacía; lo que llega en blanco
    # termina como InterpretationError y se trata igual.
    _reparacion_rechazada("   ", caplog)


def test_reparacion_cortada_por_el_techo_devuelve_el_original(caplog):
    cortada = _Resp(REPARADO[:100], stop_reason="max_tokens")
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), cortada)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


# --- el juez falla ---


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


def test_error_del_llm_en_el_juez_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_error_del_llm_en_la_reparacion_devuelve_el_original_y_loguea(caplog):
    error = anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com"))
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), error)
    with caplog.at_level(logging.WARNING, logger="interpret.revision_trato"):
        assert revisar_trato(TEXTO, "neutro", "es", cliente) == TEXTO
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_reparacion_envuelta_en_la_etiqueta_del_pedido_se_desenvuelve():
    cliente = ClienteFalso(_juez("generar vos misma el sacudón"), f"<texto>\n{REPARADO}\n</texto>")
    assert revisar_trato(TEXTO, "neutro", "es", cliente) == REPARADO
