"""Un cliente de Anthropic falso para los tests del juez y la reparación:
devuelve respuestas en orden y registra cada llamada."""

import json


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
            if not self.outer._respuestas:
                raise AssertionError("llamada al modelo que el test no esperaba")
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
