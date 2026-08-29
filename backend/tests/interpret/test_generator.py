import anthropic
import pytest

from interpret.exceptions import InterpretationError
from interpret.generator import build_interpretation
from interpret.prompts import MODEL


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Usage:
    def __init__(self, output_tokens):
        self.output_tokens = output_tokens


class _Resp:
    def __init__(self, text="Sos una persona...", stop_reason="end_turn", usage=None):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason
        self.usage = usage


class _StreamCtx:
    def __init__(self, resp, raises):
        self._resp = resp
        self._raises = raises

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        if self._raises:
            raise self._raises
        return self._resp


class FakeClient:
    def __init__(self, resp=None, raises=None):
        self._resp = resp or _Resp()
        self._raises = raises
        self.calls = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.calls.append(kwargs)
            return _StreamCtx(self.outer._resp, self.outer._raises)

    @property
    def messages(self):
        return FakeClient._Messages(self)


CHART = {"time_known": True, "placements": [{"planet": "Sun", "sign": "Cancer"}]}
CHART_NO_TIME = {"time_known": False, "placements": []}


def test_returns_text_and_uses_sonnet():
    client = FakeClient()
    text = build_interpretation(CHART, "es", "v1", client)
    assert text == "Sos una persona..."
    assert client.calls[0]["model"] == MODEL
    assert client.calls[0]["max_tokens"] == 1500


def test_system_prompt_has_cache_control():
    client = FakeClient()
    build_interpretation(CHART, "es", "v1", client)
    system = client.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


def test_no_time_known_instructs_degradation():
    client = FakeClient()
    build_interpretation(CHART_NO_TIME, "es", "v1", client)
    user_content = client.calls[0]["messages"][0]["content"]
    assert "ascendente" in user_content.lower() or "sin hora" in user_content.lower()


def test_empty_text_raises():
    client = FakeClient(resp=_Resp(text="  "))
    with pytest.raises(InterpretationError):
        build_interpretation(CHART, "es", "v1", client)


def test_truncated_raises():
    client = FakeClient(resp=_Resp(stop_reason="max_tokens"))
    with pytest.raises(InterpretationError):
        build_interpretation(CHART, "es", "v1", client)


def test_loguea_stop_reason_y_tokens_de_salida(caplog):
    """HALLAZGO 1 de code review: sin esto, la próxima decisión sobre el
    factor de tokens por palabra sale de una estimación y no de datos
    reales. El log tiene que existir SIEMPRE, incluso (sobre todo) cuando
    stop_reason es "max_tokens" — es la señal de que el tope se quedó
    corto, y se emite antes de levantar InterpretationError."""
    import logging

    client = FakeClient(resp=_Resp(usage=_Usage(output_tokens=1234)))
    with caplog.at_level(logging.INFO, logger="interpret.generator"):
        build_interpretation(CHART, "es", "v1", client)

    mensajes = [r.getMessage() for r in caplog.records]
    assert any("end_turn" in m and "1234" in m for m in mensajes)


def test_loguea_stop_reason_aunque_la_respuesta_venga_truncada(caplog):
    import logging

    client = FakeClient(resp=_Resp(stop_reason="max_tokens", usage=_Usage(output_tokens=1500)))
    with caplog.at_level(logging.INFO, logger="interpret.generator"):
        with pytest.raises(InterpretationError):
            build_interpretation(CHART, "es", "v1", client)

    mensajes = [r.getMessage() for r in caplog.records]
    assert any("max_tokens" in m and "1500" in m for m in mensajes)


def test_anthropic_error_wrapped():
    client = FakeClient(raises=anthropic.AnthropicError("boom"))
    with pytest.raises(InterpretationError):
        build_interpretation(CHART, "es", "v1", client)


def test_user_content_matches_lang():
    # El texto salía en castellano aunque lang=en: la instrucción del user
    # message estaba fija en español y le ganaba al system prompt.
    client = FakeClient()
    build_interpretation(CHART, "en", "v1", client)
    user_content = client.calls[0]["messages"][0]["content"]
    assert "Interpret this natal chart" in user_content
    assert "Interpretá" not in user_content

    client_pt = FakeClient()
    build_interpretation(CHART_NO_TIME, "pt", "v1", client_pt)
    content_pt = client_pt.calls[0]["messages"][0]["content"]
    assert "Interprete este mapa astral" in content_pt
    assert "ascendente" in content_pt.lower()  # nota de degradación en pt


def test_translate_uses_cheap_model_and_target_lang():
    from interpret.generator import translate_interpretation
    from interpret.prompts import TRANSLATE_MODEL

    client = FakeClient()
    out = translate_interpretation("## Título\nUn texto astrológico.", "en", client)
    call = client.calls[0]
    assert call["model"] == TRANSLATE_MODEL
    assert TRANSLATE_MODEL != MODEL  # traducir no paga precio de Sonnet
    assert "English" in call["system"][0]["text"]
    assert "## Título" in call["messages"][0]["content"]
    assert out == "Sos una persona..."


def test_el_modelo_es_sonnet_5():
    # Fija el identificador exacto del modelo del informe: un typo o un
    # sufijo de fecha de más rompería la generación en producción sin que
    # ningún otro test lo note (los fakes no validan el nombre del modelo).
    from interpret.prompts import MODEL
    assert MODEL == "claude-sonnet-5"
