import threading

import pytest
from django.db import connection, connections

from api import informe_service
from api.models import Account, BirthData, Chart, Interpretation, InterpretationSection
from interpret.prompts import PROMPT_VERSION, SECCION_BREVE, SECCIONES

pytestmark = pytest.mark.django_db

# SQLite serializa la base entera y no ejercita una carrera real entre
# conexiones: un "pasa" ahí sería falso verde. Mismo criterio que
# tests/api/test_ledger_concurrencia.py.
requiere_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="necesita una carrera real entre conexiones; SQLite la serializa",
)


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


def test_traduce_al_tier_correcto_cuando_hay_dos_productos_en_la_carta(chart, account):
    """Fix round 1, Important 2: el `get_or_create` de `destino` filtraba
    sólo por (chart, lang, prompt_version), sin tier. Con dos productos ese
    filtro puede matchear DOS filas —una por tier— y Django levanta
    `MultipleObjectsReturned`, que el `except Exception` de
    `completar_generacion` traga y loguea sin dejar rastro (y sin borrar la
    fila vacía que `iniciar_generacion` había creado). Reproduce: existe un
    `largo/en` completo, se traduce un `corto/es` hacia "en" — tiene que
    crear/encontrar el `corto/en`, sin tocar el `largo/en`."""
    largo_en = Interpretation.objects.create(
        chart=chart, lang="en", prompt_version=PROMPT_VERSION, tier="largo",
        account=account, completa=True,
    )
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=largo_en, slug=s.slug, orden=i, texto="ya estaba",
        )

    corto_es = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, tier="corto",
        account=account, completa=True,
    )
    InterpretationSection.objects.create(
        interpretation=corto_es, slug=SECCION_BREVE.slug, orden=0, texto="texto " * 200,
    )

    informe_service.traducir_informe(corto_es, "en", ClienteFalso())

    corto_en = Interpretation.objects.get(
        chart=chart, lang="en", tier="corto", prompt_version=PROMPT_VERSION,
    )
    assert corto_en.secciones.count() == 1
    assert corto_en.completa is True

    largo_en.refresh_from_db()
    assert largo_en.secciones.count() == 8  # intacto: la traducción del corto no lo tocó


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


# --- carrera real entre dos llamadas concurrentes (sólo Postgres) ---


def _en_hilos(fn, veces: int):
    """Corre `fn` en `veces` hilos a la vez y devuelve (resultados, errores).
    Calcado de `tests/api/test_ledger_concurrencia.py`."""
    resultados, errores = [], []
    barrera = threading.Barrier(veces)

    def worker(i):
        try:
            barrera.wait()
            resultados.append(fn(i))
        except Exception as exc:  # noqa: BLE001 - se inspeccionan en el test
            errores.append(exc)
        finally:
            connections.close_all()

    hilos = [threading.Thread(target=worker, args=(i,)) for i in range(veces)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)
    return resultados, errores


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_dos_traducciones_concurrentes_de_la_misma_carta_no_duplican_ni_explotan():
    """Dos llamadas a `traducir_informe` para el mismo origen y el mismo
    idioma, en paralelo, con conexiones de verdad (no la serialización de un
    solo hilo/una sola transacción). El `unique_together` de
    `InterpretationSection` es la red de seguridad: esto prueba que la red
    no deja pasar un 500 sin atrapar cuando efectivamente hace su trabajo."""
    acc = Account.objects.create(free_balance=1, paid_balance=0)
    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    chart = Chart.objects.create(birth_data=bd, data={}, engine_version="test", account=acc)
    origen = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=acc, completa=True,
    )
    for i, s in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=origen, slug=s.slug, orden=i, texto="texto " * 500,
        )

    resultados, errores = _en_hilos(
        lambda _i: informe_service.traducir_informe(origen, "en", ClienteFalso()), 2,
    )

    assert not errores, f"una traducción concurrente terminó en excepción: {errores}"
    assert len(resultados) == 2

    destino = Interpretation.objects.get(chart=chart, lang="en", prompt_version=PROMPT_VERSION)
    slugs = list(destino.secciones.values_list("slug", flat=True))
    assert len(slugs) == 8
    assert len(set(slugs)) == 8  # ninguna sección duplicada por slug
