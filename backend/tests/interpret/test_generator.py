import anthropic
import pytest

from interpret.exceptions import InterpretationError
from interpret.generator import build_interpretation
from interpret.prompts import MODEL


class _Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text="Sos una persona...", stop_reason="end_turn"):
        self.content = [_Block(text)]
        self.stop_reason = stop_reason


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
