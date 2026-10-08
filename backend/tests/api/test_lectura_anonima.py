import time

import pytest
from django.core.cache import cache
from django.utils import timezone

from api import cupo_diario, lectura_anonima as la
from api.identity import hash_token
from api.models import Account, Chart, CupoDiario, Interpretation, Movimiento

pytestmark = pytest.mark.django_db

DATOS = {"sol": "escorpio"}  # el servicio no mira adentro: los datos ya vienen calculados


@pytest.fixture(autouse=True)
def _limpio(settings, monkeypatch):
    cache.clear()
    settings.INTERPRETATION_ANON_DAILY_CAP = 2
    settings.LECTURA_ANONIMA_CONCURRENCIA = 3
    monkeypatch.setattr(la, "_build_client", lambda: object())
    # El hilo corre en línea: el test ve el resultado al volver de `pedir`.
    monkeypatch.setattr(la, "_arrancar_en_hilo", la.generar)


@pytest.fixture
def breve(monkeypatch):
    llamadas = []

    def escribir(data, lang, trato, client):
        llamadas.append((data, lang, trato))
        return f"breve {lang}"

    monkeypatch.setattr(la.informe_service, "escribir_breve", escribir)
    return llamadas


def _usados():
    fila = CupoDiario.objects.filter(ambito=cupo_diario.ANONIMO).first()
    return fila.usados if fila else 0


def si():
    return True


def test_camino_feliz_y_el_get_borra_la_entrada(breve):
    pedido = la.pedir(DATOS, "es", "", None, si)
    assert pedido.estado == "generando" and pedido.token
    assert breve == [(DATOS, "es", "")]
    resultado = la.estado(pedido.token)
    assert resultado["estado"] == "lista"
    assert resultado["texto"] == "breve es"
    assert resultado["lang"] == "es"
    assert resultado["disclaimer"]
    assert la.estado(pedido.token) is None  # RF4: la entrada ya no existe


def test_no_crea_filas(breve):
    antes = [m.objects.count() for m in (Chart, Interpretation, Account, Movimiento)]
    pedido = la.pedir(DATOS, "es", "", None, si)
    la.estado(pedido.token)
    assert [m.objects.count() for m in (Chart, Interpretation, Account, Movimiento)] == antes


def test_la_cache_no_guarda_datos_de_nacimiento(breve, monkeypatch):
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: None)  # queda en `generando`
    pedido = la.pedir(DATOS, "es", "", None, si)
    entrada = cache.get(f"lectura_anonima:{hash_token(pedido.token)}")
    assert set(entrada) <= {"estado", "lang", "iniciado", "fecha_cupo", "texto"}


def test_con_la_lectura_lista_otro_pedido_da_usado(breve):
    pedido = la.pedir(DATOS, "es", "", None, si)
    la.estado(pedido.token)
    with pytest.raises(la.Usado):
        la.pedir(DATOS, "es", "", pedido.token, si)


def test_generando_no_lanza_otro_hilo(breve, monkeypatch):
    lanzados = []
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: lanzados.append(a))
    pedido = la.pedir(DATOS, "es", "", None, si)
    otra = la.pedir(DATOS, "es", "", pedido.token, si)
    assert otra.token == pedido.token and otra.estado == "generando"
    assert len(lanzados) == 1
    assert _usados() == 1


def test_fallida_devuelve_el_cupo_y_deja_reintentar(monkeypatch):
    def rompe(*a):
        raise RuntimeError("anthropic caído")

    monkeypatch.setattr(la.informe_service, "escribir_breve", rompe)
    pedido = la.pedir(DATOS, "es", "", None, si)
    assert la.estado(pedido.token) == {"estado": "fallida"}
    assert _usados() == 0
    monkeypatch.setattr(la.informe_service, "escribir_breve", lambda *a: "ahora sí")
    la.pedir(DATOS, "es", "", pedido.token, si)
    assert la.estado(pedido.token)["texto"] == "ahora sí"


def test_sin_cupo(breve):
    la.pedir(DATOS, "es", "", None, si)
    la.pedir(DATOS, "es", "", None, si)
    with pytest.raises(la.SinCupo):
        la.pedir(DATOS, "es", "", None, si)


def test_cupo_de_cuenta_lleno_no_frena_al_anonimo(breve):
    CupoDiario.objects.create(fecha=timezone.now().date(), ambito=cupo_diario.CUENTA, usados=999)
    la.pedir(DATOS, "es", "", None, si)


def test_mantenimiento(breve, monkeypatch):
    monkeypatch.setattr(la.mantenimiento, "activo", lambda: True)
    with pytest.raises(la.Mantenimiento):
        la.pedir(DATOS, "es", "", None, si)


def test_ocupado_no_reserva_cupo_ni_cuenta_para_la_ip(breve, settings):
    settings.LECTURA_ANONIMA_CONCURRENCIA = 1
    cache.add("lectura_anonima:slot:0", "otro", timeout=90)
    contadas = []
    with pytest.raises(la.Ocupado):
        la.pedir(DATOS, "es", "", None, lambda: contadas.append(1) or True)
    assert contadas == [] and _usados() == 0


def test_ip_rechazada_libera_el_slot_y_no_reserva(breve):
    with pytest.raises(la.PorIP):
        la.pedir(DATOS, "es", "", None, lambda: False)
    assert _usados() == 0
    assert cache.get("lectura_anonima:slot:0") is None


def test_el_slot_se_libera_al_terminar(breve):
    la.pedir(DATOS, "es", "", None, si)
    assert cache.get("lectura_anonima:slot:0") is None


def test_caida_devuelve_cupo_una_sola_vez(breve, monkeypatch):
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: None)
    pedido = la.pedir(DATOS, "es", "", None, si)
    clave = f"lectura_anonima:{hash_token(pedido.token)}"
    entrada = cache.get(clave)
    entrada["iniciado"] = time.time() - 100
    cache.set(clave, entrada, 900)
    assert la.estado(pedido.token) == {"estado": "fallida"}
    assert la.estado(pedido.token) == {"estado": "fallida"}
    assert _usados() == 0
    # Si el hilo «resucita» y falla después, no devuelve otra vez.
    def rompe(*a):
        raise RuntimeError("tarde")

    monkeypatch.setattr(la.informe_service, "escribir_breve", rompe)
    la.generar(hash_token(pedido.token), DATOS, "es", "", 0, timezone.now().date(), entrada["iniciado"])
    assert _usados() == 0


def _entrada_caida(token):
    clave = f"lectura_anonima:{hash_token(token)}"
    entrada = cache.get(clave)
    entrada["iniciado"] = time.time() - 100
    cache.set(clave, entrada, 900)
    return entrada


def test_carrera_del_lock_no_lanza_dos_veces(breve, monkeypatch):
    """Otro pedido escribió la entrada entre la primera lectura y el lock."""
    lanzados = []
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: lanzados.append(a))
    primero = la.pedir(DATOS, "es", "", None, si)
    clave = f"lectura_anonima:{hash_token(primero.token)}"
    reales = cache.get
    vistas = {"n": 0}

    def get_ciego(k, *a, **kw):
        if k == clave and vistas["n"] == 0:
            vistas["n"] += 1
            return None  # la lectura previa al lock no ve la entrada
        return reales(k, *a, **kw)

    monkeypatch.setattr(la.cache, "get", get_ciego)
    otro = la.pedir(DATOS, "es", "", primero.token, si)
    assert otro.estado == "generando"
    assert len(lanzados) == 1 and _usados() == 1


def test_carrera_del_lock_con_marca_da_usado(breve, monkeypatch):
    token = "t" * 20
    h = hash_token(token)
    reales = cache.get
    llamadas = {"n": 0}

    def get(k, *a, **kw):
        if k == f"lectura_anonima:usado:{h}":
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                return None
            return 1
        return reales(k, *a, **kw)

    monkeypatch.setattr(la.cache, "get", get)
    with pytest.raises(la.Usado):
        la.pedir(DATOS, "es", "", token, si)
    assert _usados() == 0


def test_caida_relanzada_por_post_devuelve_el_cupo_viejo(breve, monkeypatch):
    monkeypatch.setattr(la, "_arrancar_en_hilo", lambda *a: None)
    pedido = la.pedir(DATOS, "es", "", None, si)
    _entrada_caida(pedido.token)
    la.pedir(DATOS, "es", "", pedido.token, si)
    assert _usados() == 1
    nueva = cache.get(f"lectura_anonima:{hash_token(pedido.token)}")
    assert nueva["estado"] == "generando"
    la.estado(pedido.token)
    assert _usados() == 1


def test_el_slot_ajeno_no_se_borra(breve):
    cache.add("lectura_anonima:slot:0", "otro", timeout=90)
    la.generar("mio", DATOS, "es", "", 0, timezone.now().date(), time.time())
    assert cache.get("lectura_anonima:slot:0") == "otro"


def test_error_tras_reservar_libera_slot_y_cupo(breve, monkeypatch):
    reales = cache.set

    def set_roto(k, *a, **kw):
        if k.startswith("lectura_anonima:") and ":" not in k[len("lectura_anonima:"):]:
            raise RuntimeError("caché caída")
        return reales(k, *a, **kw)

    monkeypatch.setattr(la.cache, "set", set_roto)
    with pytest.raises(RuntimeError):
        la.pedir(DATOS, "es", "", None, si)
    assert _usados() == 0
    assert cache.get("lectura_anonima:slot:0") is None


def test_error_en_permitir_libera_el_slot(breve):
    def rompe():
        raise RuntimeError("ip")

    with pytest.raises(RuntimeError):
        la.pedir(DATOS, "es", "", None, rompe)
    assert cache.get("lectura_anonima:slot:0") is None
    assert _usados() == 0
