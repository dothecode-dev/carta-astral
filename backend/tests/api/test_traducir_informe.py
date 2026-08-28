import pytest

from api import informe_service
from api.models import Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION, SECCIONES

pytestmark = pytest.mark.django_db


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
    de la traducción."""

    def __init__(self, falla_en=None):
        self.falla_en = falla_en
        self.llamadas = []

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.llamadas.append(kwargs)
            if self.outer.falla_en is not None and len(self.outer.llamadas) == self.outer.falla_en:
                raise RuntimeError("cayó la API")
            return _StreamCtx(_Respuesta())

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def _crear_secciones(interpretacion):
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=s.slug, orden=i, texto="texto " * 500,
        )
    interpretacion.completa = True
    interpretacion.save(update_fields=["completa"])


def test_traduce_seccion_por_seccion_y_no_de_una(interpretacion):
    # 6.400 palabras no entran en una sola llamada de traducción.
    _crear_secciones(interpretacion)

    cliente = ClienteFalso()
    informe_service.traducir_informe(interpretacion, "en", cliente)

    assert len(cliente.llamadas) == 8
    destino = Interpretation.objects.get(
        chart=interpretacion.chart, lang="en", prompt_version=PROMPT_VERSION,
    )
    assert destino.secciones.count() == 8
    assert destino.completa is True
    assert "texto traducido" in destino.text


def test_no_debita_ni_devuelve_creditos(interpretacion, monkeypatch):
    from api import ledger

    def _explota(*args, **kwargs):
        raise AssertionError("traducir_informe no debe tocar el ledger")

    monkeypatch.setattr(ledger, "charge", _explota)
    monkeypatch.setattr(ledger, "devolver", _explota)
    _crear_secciones(interpretacion)

    informe_service.traducir_informe(interpretacion, "en", ClienteFalso())


def test_si_falla_a_mitad_conserva_lo_traducido_y_no_marca_completa(interpretacion):
    _crear_secciones(interpretacion)

    with pytest.raises(RuntimeError):
        informe_service.traducir_informe(interpretacion, "en", ClienteFalso(falla_en=5))

    destino = Interpretation.objects.get(
        chart=interpretacion.chart, lang="en", prompt_version=PROMPT_VERSION,
    )
    assert destino.secciones.count() == 4
    assert destino.completa is False


def test_al_reanudar_no_vuelve_a_traducir_lo_ya_hecho(interpretacion):
    _crear_secciones(interpretacion)

    with pytest.raises(RuntimeError):
        informe_service.traducir_informe(interpretacion, "en", ClienteFalso(falla_en=5))

    segundo = ClienteFalso()
    informe_service.traducir_informe(interpretacion, "en", segundo)

    # Cuatro ya estaban traducidas: sólo se piden las cuatro que faltan.
    assert len(segundo.llamadas) == 4
    destino = Interpretation.objects.get(
        chart=interpretacion.chart, lang="en", prompt_version=PROMPT_VERSION,
    )
    assert destino.secciones.count() == 8
    assert destino.completa is True


def test_traducir_dos_veces_no_duplica_secciones(interpretacion):
    _crear_secciones(interpretacion)

    informe_service.traducir_informe(interpretacion, "en", ClienteFalso())
    segundo = ClienteFalso()
    informe_service.traducir_informe(interpretacion, "en", segundo)

    assert len(segundo.llamadas) == 0
    destino = Interpretation.objects.get(
        chart=interpretacion.chart, lang="en", prompt_version=PROMPT_VERSION,
    )
    assert destino.secciones.count() == 8


def test_el_tope_de_traduccion_alcanza_para_la_seccion_mas_larga():
    """`TRANSLATE_MAX_TOKENS` tiene que sostener el mismo criterio de holgura
    que usa `build_seccion` (`seccion.palabras * 2`) para la sección más
    larga del catálogo (tensiones, 1000 palabras) — y con margen: una sección
    real puede superar su objetivo nominal (`build_seccion` la genera con un
    tope de hasta el doble de tokens, no un límite de palabras), así que el
    piso exacto (2000) no alcanza. Antes de esta tarea valía 2000, dimensionado
    para una lectura corta de 400 a 700 palabras; una traducción cortada por
    `max_tokens` es una sección mutilada que `_stream_text` seguiría
    persistiendo como buena si el tope no alcanza."""
    from interpret.prompts import TRANSLATE_MAX_TOKENS

    mas_larga = max(s.palabras for s in SECCIONES)
    assert TRANSLATE_MAX_TOKENS > mas_larga * 2
    assert TRANSLATE_MAX_TOKENS == 2500


def test_destino_hereda_el_estado_incompleto_del_origen(interpretacion):
    """Si el origen todavía no terminó de generarse, la traducción de lo que
    hay hasta ahora no puede marcarse completa: eso sería mentir sobre un
    informe que en realidad sigue a medio escribir."""
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug=SECCIONES[0].slug, orden=0, texto="texto " * 50,
    )
    assert interpretacion.completa is False

    informe_service.traducir_informe(interpretacion, "en", ClienteFalso())

    destino = Interpretation.objects.get(
        chart=interpretacion.chart, lang="en", prompt_version=PROMPT_VERSION,
    )
    assert destino.secciones.count() == 1
    assert destino.completa is False
