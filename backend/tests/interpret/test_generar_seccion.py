import pytest

from interpret.exceptions import InterpretationError
from interpret.generator import build_interpretation, build_seccion
from interpret.prompts import MAX_TOKENS, SECCIONES


class _Bloque:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Respuesta:
    def __init__(self, text="texto de la sección", stop_reason="end_turn"):
        self.content = [_Bloque(text)]
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


class ClienteFalso:
    """Captura lo que se le manda al modelo y devuelve una respuesta fija,
    igual que el streaming real: `messages.stream(...)` como context manager
    y el texto final vía `get_final_message()`."""

    def __init__(self, resp=None, raises=None):
        self._resp = resp or _Respuesta()
        self._raises = raises
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.llamadas.append(kwargs)
            return _StreamCtx(self.outer._resp, self.outer._raises)

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def test_la_primera_seccion_no_recibe_contexto_previo():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[0], "es", "", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "YA ESCRITO" not in enviado


def test_las_siguientes_reciben_lo_ya_escrito_para_no_repetirse():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[2], "es", "Ya se habló del Sol en Leo.", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "Ya se habló del Sol en Leo." in enviado


def test_el_foco_de_la_seccion_viaja_en_el_pedido():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[1], "es", "", c)
    enviado = c.llamadas[0]["messages"][0]["content"]
    assert "Mercurio" in enviado


def test_devuelve_el_texto_del_modelo():
    assert build_seccion({"planets": []}, SECCIONES[0], "es", "", ClienteFalso()) == "texto de la sección"


def test_el_tope_de_tokens_acompana_al_largo_pedido():
    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[4], "es", "", c)  # tensiones: 1000 palabras
    assert c.llamadas[0]["max_tokens"] >= 1000 * 2


def test_el_factor_de_tokens_por_palabra_alcanza_al_menos_el_ratio_de_build_interpretation():
    """HALLAZGO 1 de code review: `seccion.palabras * 2` es insuficiente. El
    español y el portugués corren 1,7 a 2,2 tokens por palabra, así que
    "tensiones" (1000 palabras, techo de 2000 tokens con el factor viejo)
    cruza el techo con frecuencia y el fallo es terminal (ver
    `interpret/prompts.py::SECCION_TOKENS_POR_PALABRA`).

    El factor de las secciones tiene que igualar o superar el que se le da a
    `build_interpretation` en su peor caso, porque a diferencia de
    `build_interpretation` el `system` de una sección no fija ningún largo (lo
    fija sólo el pedido), así que no hay ninguna presión adicional que mantenga
    a la sección corta.

    El peor caso es el extremo LARGO del rango (700 palabras), que es donde el
    techo se pone a prueba: si el texto sale en el extremo corto sobra techo, no
    falta. Este test comparaba contra 400 —"el objetivo más corto: la mayor
    exigencia"— y ese razonamiento estaba invertido; con `MAX_TOKENS` en 1500
    pasaba igual, y la lectura breve fallaba el 100% de las veces en producción
    (ver `tests/interpret/test_techo_lectura_breve.py`)."""
    from interpret.prompts import SECCION_TOKENS_POR_PALABRA

    # 700 palabras: el extremo largo del rango que pide el system, donde el
    # techo de build_interpretation se pone a prueba de verdad.
    ratio_build_interpretation = MAX_TOKENS / 700
    assert SECCION_TOKENS_POR_PALABRA >= ratio_build_interpretation

    c = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[4], "es", "", c)  # tensiones: 1000 palabras
    assert c.llamadas[0]["max_tokens"] == 1000 * SECCION_TOKENS_POR_PALABRA


def test_una_seccion_truncada_por_max_tokens_falla():
    """Garantía de que una sección cortada a la mitad no se persiste como si
    estuviera completa: _stream_text valida stop_reason y levanta."""
    c = ClienteFalso(resp=_Respuesta(stop_reason="max_tokens"))
    with pytest.raises(InterpretationError):
        build_seccion({"planets": []}, SECCIONES[0], "es", "", c)


def test_el_system_de_seccion_no_fija_un_largo_y_difiere_del_de_interpretacion():
    """El largo de una sección lo fija el pedido (varía 600-1000 según la
    sección), no el system: si el system dijera "400 a 700 palabras" como el
    de la interpretación corta, el informe completo saldría muy por debajo de
    las 6400 palabras que promete el catálogo."""
    c_seccion = ClienteFalso()
    build_seccion({"planets": []}, SECCIONES[0], "es", "", c_seccion)
    system_seccion = c_seccion.llamadas[0]["system"][0]["text"]

    for palabra_prohibida in ("400", "700", "words", "palabras", "palavras"):
        assert palabra_prohibida not in system_seccion.lower()

    c_interpretacion = ClienteFalso()
    build_interpretation({"planets": []}, "es", "v2", c_interpretacion)
    system_interpretacion = c_interpretacion.llamadas[0]["system"][0]["text"]

    assert system_seccion != system_interpretacion
