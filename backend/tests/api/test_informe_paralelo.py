"""El informe se escribe con las secciones a la vez (spec 2026-10-10, Fase 1).

Qué fijan estos tests, y por qué importa cada cosa:

- que de verdad corran a la vez (un cliente falso con barrera: si el código
  fuera en serie, la barrera nunca se cumple y el test falla);
- que ningún hilo de trabajo toque la base (sólo el coordinador: sin eso cada
  hilo abre una conexión que nadie cierra);
- que el orden de llegada no cambie el orden del informe;
- que un fallo no tire el trabajo de las demás y que perder el lock corte
  la persistencia (contratos de `generar_informe` y `completar_generacion`);
- que la síntesis, que habla de «todo lo anterior», espere a las demás y vea
  su resumen.
"""

import logging
import threading
import time

import pytest
from django.core.cache import cache

from api import informe_service, interpretation_service
from api.sujetos import sujeto_natal
from interpret.prompts import SECCIONES

pytestmark = pytest.mark.django_db

TOKEN = "tok-paralelo"
ORDEN_POR_TITULO = {s.titulo["es"]: i for i, s in enumerate(SECCIONES)}


@pytest.fixture(autouse=True)
def _sin_revision_del_trato(monkeypatch):
    monkeypatch.setattr(informe_service, "revisar_trato", lambda texto, trato, lang, client: texto)


@pytest.fixture(autouse=True)
def lock_tomado(chart):
    key = interpretation_service._lock_key(sujeto_natal(chart), "largo")
    cache.set(key, TOKEN, timeout=600)
    yield
    cache.delete(key)


class _Bloque:
    def __init__(self, text):
        self.type, self.text = "text", text


class _Respuesta:
    def __init__(self, text):
        self.content, self.stop_reason = [_Bloque(text)], "end_turn"


class _Stream:
    def __init__(self, resp):
        self._resp = resp

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._resp


class ClienteConcurrente:
    """Cliente falso seguro entre hilos.

    `n_a_la_vez`: las primeras `n` llamadas esperan en una barrera hasta que
    estén las `n` en vuelo; si el código fuera en serie, la barrera se rompe
    por timeout y la llamada levanta. `pico` es el máximo de llamadas en vuelo.
    `demora` y `falla` se deciden por el título de la sección del pedido."""

    def __init__(self, n_a_la_vez=0, demora=None, falla=()):
        self.llamadas = []
        self.pico = 0
        self._en_vuelo = 0
        self._lock = threading.Lock()
        self._barrera = threading.Barrier(n_a_la_vez, timeout=10) if n_a_la_vez else None
        self._pendientes_de_barrera = n_a_la_vez
        self._demora = demora or {}
        self._falla = set(falla)

    @property
    def messages(self):
        return self

    def _titulo(self, contenido):
        for titulo in ORDEN_POR_TITULO:
            if f"«{titulo}»" in contenido:
                return titulo
        return None

    def stream(self, **kwargs):
        contenido = kwargs["messages"][0]["content"]
        titulo = self._titulo(contenido)
        with self._lock:
            self.llamadas.append(kwargs)
            numero = len(self.llamadas)
            self._en_vuelo += 1
            self.pico = max(self.pico, self._en_vuelo)
            esperar = self._barrera is not None and self._pendientes_de_barrera > 0
            if esperar:
                self._pendientes_de_barrera -= 1
        try:
            if esperar:
                self._barrera.wait()
            time.sleep(self._demora.get(titulo, 0))
            if titulo in self._falla:
                raise RuntimeError(f"cayó la API en {titulo}")
            return _Stream(_Respuesta(f"TEXTO-{numero}-{titulo}"))
        finally:
            with self._lock:
                self._en_vuelo -= 1


def _titulos_de(cliente):
    return [cliente._titulo(ll["messages"][0]["content"]) for ll in cliente.llamadas]


def test_las_secciones_se_escriben_a_la_vez(interpretacion):
    # Siete a la vez: la síntesis, la octava, espera a las demás.
    cliente = ClienteConcurrente(n_a_la_vez=7)
    assert informe_service.generar_informe(interpretacion, cliente, TOKEN) is True
    interpretacion.refresh_from_db()
    assert interpretacion.completa and interpretacion.secciones.count() == 8
    assert cliente.pico == 7


def test_con_paralelismo_1_se_escribe_en_serie_y_en_orden_del_catalogo(interpretacion, settings):
    settings.INFORME_PARALELISMO = 1
    cliente = ClienteConcurrente()
    informe_service.generar_informe(interpretacion, cliente, TOKEN)
    assert cliente.pico == 1
    assert _titulos_de(cliente) == [s.titulo["es"] for s in SECCIONES]


def test_la_sintesis_va_al_final_y_es_la_unica_que_ve_lo_escrito(interpretacion):
    cliente = ClienteConcurrente()
    informe_service.generar_informe(interpretacion, cliente, TOKEN)
    titulos = _titulos_de(cliente)
    assert titulos[-1] == "Síntesis"
    pedidos = [ll["messages"][0]["content"] for ll in cliente.llamadas]
    assert all("YA ESCRITO" not in p for p in pedidos[:-1])
    # El resumen de las siete llega a la última.
    assert "YA ESCRITO" in pedidos[-1] and pedidos[-1].count("TEXTO-") >= 7


def test_el_informe_sale_en_orden_aunque_las_secciones_terminen_al_reves(interpretacion):
    # La primera del catálogo es la más lenta: termina la última.
    demora = {s.titulo["es"]: 0.03 * (len(SECCIONES) - i) for i, s in enumerate(SECCIONES[:-1])}
    informe_service.generar_informe(interpretacion, ClienteConcurrente(demora=demora), TOKEN)
    interpretacion.refresh_from_db()
    por_orden = list(interpretacion.secciones.order_by("orden").values_list("slug", flat=True))
    assert por_orden == [s.slug for s in SECCIONES]
    por_llegada = list(interpretacion.secciones.order_by("id").values_list("slug", flat=True))
    assert por_llegada != por_orden  # el test de verdad las cruzó
    assert interpretacion.text.split("\n\n")[0].endswith(SECCIONES[0].titulo["es"])


def test_ningun_hilo_de_trabajo_toca_la_base(interpretacion, monkeypatch):
    import django.db.backends.base.base as base

    original = base.BaseDatabaseWrapper.ensure_connection
    hilos = []

    def espia(self):
        nombre = threading.current_thread().name
        if nombre.startswith("informe"):
            hilos.append(nombre)
        return original(self)

    monkeypatch.setattr(base.BaseDatabaseWrapper, "ensure_connection", espia)
    informe_service.generar_informe(interpretacion, ClienteConcurrente(), TOKEN)
    assert hilos == []


def test_un_fallo_no_tira_el_trabajo_de_las_demas_y_el_reintento_retoma_lo_que_falta(interpretacion):
    con_falla = ClienteConcurrente(falla={SECCIONES[1].titulo["es"]})
    with pytest.raises(RuntimeError):
        informe_service.generar_informe(interpretacion, con_falla, TOKEN)
    interpretacion.refresh_from_db()
    # Las seis hermanas de la que falló están escritas; la síntesis no se intentó.
    assert interpretacion.secciones.count() == 6
    assert interpretacion.completa is False
    assert "Síntesis" not in _titulos_de(con_falla)

    sano = ClienteConcurrente()
    informe_service.generar_informe(interpretacion, sano, TOKEN)
    interpretacion.refresh_from_db()
    assert len(sano.llamadas) == 2  # la que faltaba + la síntesis
    assert interpretacion.completa and interpretacion.secciones.count() == 8


def test_perder_el_lock_con_trabajo_pendiente_corta_la_persistencia(interpretacion, monkeypatch):
    monkeypatch.setattr(informe_service, "renovar_lock", lambda *a: False)
    cliente = ClienteConcurrente()
    assert informe_service.generar_informe(interpretacion, cliente, TOKEN) is False
    interpretacion.refresh_from_db()
    assert interpretacion.secciones.count() == 1 and interpretacion.completa is False


def test_el_lock_se_renueva_tras_cada_seccion_persistida(interpretacion, monkeypatch):
    renovaciones = []
    monkeypatch.setattr(informe_service, "renovar_lock", lambda *a: renovaciones.append(1) or True)
    informe_service.generar_informe(interpretacion, ClienteConcurrente(), TOKEN)
    assert len(renovaciones) == 8


def test_loguea_cuanto_tardo_cada_informe_sin_el_texto(interpretacion, caplog):
    with caplog.at_level(logging.INFO, logger="api.informe_service"):
        informe_service.generar_informe(interpretacion, ClienteConcurrente(), TOKEN)
    lineas = [r.getMessage() for r in caplog.records if "informe generado" in r.getMessage()]
    assert len(lineas) == 1
    for esperado in ("secciones=8", "paralelismo_max=", "total_s=", "primera_s="):
        assert esperado in lineas[0], esperado
    assert "TEXTO-" not in lineas[0]


# --- la traducción ---


def test_la_traduccion_tambien_va_a_la_vez_y_conserva_el_orden(interpretacion_completa):
    origen = interpretacion_completa
    key = interpretation_service._lock_key(origen.sujeto, origen.tier)
    cache.set(key, TOKEN, timeout=600)
    cliente = ClienteConcurrente(n_a_la_vez=8)
    assert informe_service.traducir_informe(origen, "en", cliente, TOKEN) is True
    assert cliente.pico == 8
    from api.models import Interpretation

    destino = Interpretation.objects.get(sujeto=origen.sujeto, lang="en", tier=origen.tier)
    assert destino.completa and destino.secciones.count() == 8
    assert list(destino.secciones.values_list("slug", flat=True)) == [s.slug for s in SECCIONES]


# --- hallazgos del code review de d398708 ---


def test_la_segunda_ola_vacia_no_consulta_el_resumen(interpretacion, monkeypatch):
    """Si la síntesis ya estaba escrita no hay segunda ola: no se arma un
    resumen que nadie va a usar."""
    from api.models import InterpretationSection

    InterpretationSection.objects.create(
        interpretation=interpretacion, slug="sintesis", orden=len(SECCIONES) - 1, texto="ya estaba",
    )
    consultas = []
    original = informe_service.resumen_previo
    monkeypatch.setattr(
        informe_service, "resumen_previo", lambda i: consultas.append(1) or original(i),
    )
    informe_service.generar_informe(interpretacion, ClienteConcurrente(), TOKEN)
    assert consultas == []


def test_generar_no_modifica_los_datos_que_comparten_los_hilos(interpretacion):
    """`_Contexto` es inmutable sólo de superficie: los hilos comparten el dict
    de la carta. Ninguna función de interpret/ puede mutarlo."""
    import copy

    carta = interpretacion.sujeto.natal_de
    antes = copy.deepcopy(carta.data)
    informe_service.generar_informe(interpretacion, ClienteConcurrente(), TOKEN)
    assert carta.data == antes


def test_ningun_hilo_toca_la_base_tampoco_al_traducir(interpretacion_completa, monkeypatch):
    import django.db.backends.base.base as base

    origen = interpretacion_completa
    cache.set(interpretation_service._lock_key(origen.sujeto, origen.tier), TOKEN, timeout=600)
    original = base.BaseDatabaseWrapper.ensure_connection
    hilos = []

    def espia(self):
        if threading.current_thread().name.startswith("informe"):
            hilos.append(threading.current_thread().name)
        return original(self)

    monkeypatch.setattr(base.BaseDatabaseWrapper, "ensure_connection", espia)
    informe_service.traducir_informe(origen, "en", ClienteConcurrente(), TOKEN)
    assert hilos == []
