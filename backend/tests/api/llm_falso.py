"""Doble del cliente de Anthropic con la interfaz real de streaming.

Lo comparten los tests de traducción y los del informe de vínculo."""


class _Bloque:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Respuesta:
    def __init__(self, text="texto traducido", stop_reason="end_turn"):
        self.content = [_Bloque(text)]
        self.stop_reason = stop_reason


class _StreamCtx:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._resp


class ClienteFalso:
    """Fake del cliente Anthropic con la interfaz real de streaming
    (`messages.stream(...)` como context manager + `get_final_message()`),
    calcado del de `tests/api/test_informe_service.py`. `falla_en` hace que
    la llamada N-ésima levante RuntimeError, para simular un corte a mitad
    de la traducción. `textos`, si se pasa, es una función que recibe el número
    de llamada (desde 1) y devuelve el texto de esa respuesta."""

    def __init__(self, falla_en=None, textos=None):
        self.falla_en = falla_en
        self.textos = textos
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.llamadas.append(kwargs)
            if self.outer.falla_en is not None and len(self.outer.llamadas) == self.outer.falla_en:
                raise RuntimeError("cayó la API")
            if self.outer.textos is not None:
                return _StreamCtx(_Respuesta(self.outer.textos(len(self.outer.llamadas))))
            return _StreamCtx(_Respuesta())

    @property
    def messages(self):
        return ClienteFalso._Messages(self)
