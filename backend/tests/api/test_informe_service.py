import pytest
from django.core.cache import cache

from api import informe_service
from api.models import InterpretationSection
from interpret.prompts import PROMPT_VERSION

pytestmark = pytest.mark.django_db

TOKEN = "tok-test"


@pytest.fixture(autouse=True)
def lock_tomado(chart):
    """Simula que ya se tomó el lock de esta carta con TOKEN, como hace
    `get_or_create_interpretation` antes de generar. Sin esto, el
    `renovar_lock` real (no mockeado) siempre devuelve False porque no hay
    ningún lock que renovar, y los tests de arriba abortarían en la primera
    sección por una razón ajena a lo que están probando."""
    key = f"interp:lock:{chart.id}:{PROMPT_VERSION}"
    cache.set(key, TOKEN, timeout=600)
    yield
    cache.delete(key)


class _Bloque:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _Respuesta:
    def __init__(self, text="cuerpo de la sección", stop_reason="end_turn"):
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
    calcado del de `tests/interpret/test_generar_seccion.py`. `falla_en` hace
    que la llamada N-ésima levante RuntimeError, para simular un corte a
    mitad de informe."""

    def __init__(self, falla_en=None):
        self.falla_en = falla_en
        self.generadas = 0

    class _Messages:
        def __init__(self, outer):
            self.outer = outer

        def stream(self, **kwargs):
            self.outer.generadas += 1
            if self.outer.falla_en is not None and self.outer.generadas == self.outer.falla_en:
                raise RuntimeError("cayó la API")
            return _StreamCtx(_Respuesta())

    @property
    def messages(self):
        return ClienteFalso._Messages(self)


def test_genera_las_ocho_secciones_y_marca_completa(interpretacion):
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == 8
    assert interpretacion.completa is True


def test_si_falla_a_mitad_conserva_lo_escrito_y_no_marca_completa(interpretacion):
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == 4
    assert interpretacion.completa is False


def test_al_reanudar_no_vuelve_a_pedir_las_secciones_ya_escritas(interpretacion):
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)
    segundo = ClienteFalso()
    informe_service.generar_informe(interpretacion, segundo, TOKEN)
    # Cuatro ya estaban: sólo se piden las cuatro que faltan.
    assert segundo.generadas == 4
    interpretacion.refresh_from_db()
    assert interpretacion.completa is True


def test_sin_hora_de_nacimiento_se_omite_la_seccion_de_casas(interpretacion):
    interpretacion.chart.data["time_known"] = False
    interpretacion.chart.save()
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    slugs = [s.slug for s in interpretacion.secciones.all()]
    assert "casas" not in slugs
    assert len(slugs) == 7


def test_el_texto_completo_se_arma_al_terminar(interpretacion):
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    interpretacion.refresh_from_db()
    # `text` se sigue llenando para no romper al PDF ni a la web mientras migran.
    assert "cuerpo de la sección" in interpretacion.text


def test_el_resumen_previo_crece_con_cada_seccion(interpretacion):
    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="firma", orden=0, texto="Sol en Leo. " * 50,
    )
    previo = informe_service.resumen_previo(interpretacion)
    assert "Sol en Leo" in previo


def test_renueva_el_lock_despues_de_cada_seccion_persistida(interpretacion, monkeypatch):
    llamadas = []

    def _renovar(chart, token):
        llamadas.append((chart.id, token))
        return True

    monkeypatch.setattr(informe_service, "renovar_lock", _renovar)
    informe_service.generar_informe(interpretacion, ClienteFalso(), TOKEN)
    assert len(llamadas) == 8
    assert all(chart_id == interpretacion.chart_id and token == TOKEN for chart_id, token in llamadas)


def test_si_pierde_el_lock_aborta_sin_completar_ni_seguir_pidiendo(interpretacion, monkeypatch):
    cliente = ClienteFalso()

    monkeypatch.setattr(informe_service, "renovar_lock", lambda chart, token: False)
    informe_service.generar_informe(interpretacion, cliente, TOKEN)
    interpretacion.refresh_from_db()
    # La sección que ya se había generado antes de perder el lock queda
    # persistida, pero no siguió pidiendo las demás ni marcó el informe
    # completo: perder el lock significa que otro proceso lo tomó y va a
    # terminar el informe por su cuenta.
    assert interpretacion.secciones.count() == 1
    assert interpretacion.completa is False
    assert cliente.generadas == 1


def test_nunca_llama_a_devolver_credito_ante_una_falla_parcial(interpretacion, monkeypatch):
    from api import ledger

    def _explota(*args, **kwargs):
        raise AssertionError("generar_informe no debe llamar a ledger.devolver")

    monkeypatch.setattr(ledger, "devolver", _explota)
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, ClienteFalso(falla_en=5), TOKEN)
