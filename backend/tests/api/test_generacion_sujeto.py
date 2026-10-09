"""Generación y locks por sujeto (parte 2 de Vínculo). El natal no cambia: lo
que cambia es de qué cuelgan la fila, el cobro y el lock.

Sobre una cuenta en blanco (`make_account()`): el fixture `account` ya trae
tres informes, y con eso «no cobró» no se podría distinguir de «cobró»."""

import pytest
from django.core.cache import cache

from api import interpretation_service as svc
from api.canje import otorgar
from api.exceptions import GenerationInProgress
from api.models import Derecho, Interpretation, Movimiento, Sujeto
from api.sujetos import sujeto_natal
from interpret.prompts import TIER_LARGO

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _cache_limpia():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def cuenta(make_account):
    return make_account()


@pytest.fixture
def carta(make_chart, cuenta):
    return make_chart(account=cuenta)


def _restante(cuenta) -> int:
    d = Derecho.objects.filter(account=cuenta, codigo_producto="informe_natal").first()
    return d.cantidad_restante if d is not None else 0


def test_la_clave_del_lock_es_por_sujeto(carta):
    s = sujeto_natal(carta)
    assert svc._lock_key(s, TIER_LARGO).startswith(f"interp:lock:s{s.pk}:")


def test_dos_sujetos_tienen_locks_distintos(carta):
    a = sujeto_natal(carta)
    b = Sujeto.objects.create(producto=Sujeto.VINCULO)
    assert svc._lock_key(a, TIER_LARGO) != svc._lock_key(b, TIER_LARGO)


def test_dos_vinculos_sin_carta_no_comparten_el_lock():
    """Si la clave dependiera de la carta, los dos vínculos (sin `natal_de`)
    caerían en la misma y la generación de uno bloquearía la del otro."""
    uno = Sujeto.objects.create(producto=Sujeto.VINCULO)
    otro = Sujeto.objects.create(producto=Sujeto.VINCULO)
    assert svc._lock_key(uno, TIER_LARGO) != svc._lock_key(otro, TIER_LARGO)


def test_iniciar_crea_la_fila_con_sujeto_y_carta_y_cobra(cuenta, carta):
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    i = svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, TIER_LARGO)
    assert i.sujeto_id == sujeto_natal(carta).pk
    assert i.chart_id == carta.pk
    assert _restante(cuenta) == 0
    assert Movimiento.objects.get(account=cuenta, tipo="consumo").sujeto_id == i.sujeto_id


def test_iniciar_dos_veces_el_mismo_sujeto_es_la_misma_fila_y_un_solo_cobro(cuenta, carta):
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:2")
    primera = svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, TIER_LARGO)
    segunda = svc.iniciar_generacion(sujeto_natal(carta), "es", cuenta, TIER_LARGO)
    assert primera.pk == segunda.pk
    assert _restante(cuenta) == 1


def test_un_hermano_en_curso_por_sujeto_da_409_y_no_cobra(cuenta, carta):
    otorgar(cuenta, "informe_natal", 2, origen="compra", external_id="p:4")
    s = sujeto_natal(carta)
    svc.iniciar_generacion(s, "es", cuenta, TIER_LARGO)
    cache.add(svc._lock_key(s, TIER_LARGO), "hilo-de-es", timeout=30)

    with pytest.raises(GenerationInProgress):
        svc.iniciar_generacion(s, "en", cuenta, TIER_LARGO)
    assert _restante(cuenta) == 1


def test_un_sujeto_que_no_es_natal_no_se_genera_todavia(cuenta):
    """Hasta la parte 3 no hay prompt ni secciones de vínculo: error explícito,
    nunca un informe natal escrito sobre datos vacíos, y sin cobrar."""
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:5")
    s = Sujeto.objects.create(producto=Sujeto.VINCULO, account=cuenta)
    with pytest.raises(NotImplementedError):
        svc.iniciar_generacion(s, "es", cuenta, TIER_LARGO)
    assert not Interpretation.objects.filter(sujeto=s).exists()
    assert _restante(cuenta) == 1


def test_completar_devuelve_sobre_el_sujeto_si_agota_los_intentos(cuenta, carta, monkeypatch):
    """La devolución tras tres intentos fallidos (RF7 de la spec) libera el
    canje del SUJETO: después se puede volver a pedir."""
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:6")
    s = sujeto_natal(carta)
    i = svc.iniciar_generacion(s, "es", cuenta, TIER_LARGO)
    Interpretation.objects.filter(pk=i.pk).update(intentos=svc.INTENTOS_MAXIMOS)
    i.refresh_from_db()

    from api import informe_service

    def falla(*args, **kwargs):
        raise RuntimeError("el modelo no contestó")

    monkeypatch.setattr(informe_service, "generar_informe", falla)
    monkeypatch.setattr(svc, "_build_client", lambda: object())

    svc.completar_generacion(i, cuenta)

    assert _restante(cuenta) == 1
    assert not Interpretation.objects.filter(pk=i.pk).exists()
    devolucion = Movimiento.objects.get(account=cuenta, tipo="devolucion")
    assert devolucion.sujeto_id == s.pk


def test_las_funciones_de_generacion_rechazan_una_carta(make_chart, cuenta):
    """CONTRAER (deploy 2): quien llama ya resolvió el sujeto. Una carta acá es
    un llamador que se quedó en el deploy 1."""
    carta = make_chart(account=cuenta)
    with pytest.raises(TypeError):
        svc.esta_generandose(carta, TIER_LARGO)
    with pytest.raises(TypeError):
        svc.iniciar_generacion(carta, "es", cuenta, TIER_LARGO)


def test_reanudar_usa_el_sujeto_de_la_fila(interpretacion, monkeypatch):
    from django.core.management import call_command

    vistos = []
    monkeypatch.setattr(svc, "completar_generacion", lambda i, acc: vistos.append(i.sujeto_id))
    call_command("reanudar_informes")
    assert vistos == [interpretacion.sujeto_id]
