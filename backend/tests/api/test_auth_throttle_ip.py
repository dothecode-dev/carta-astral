"""C1 (revisión de `puertas-de-acceso`): el techo del scope "auth" tiene que
contar por la IP de quien visita, no por la del contenedor que reenvía.

Con `NUM_PROXIES=None` (el default de DRF), `SimpleRateThrottle.get_ident()`
usa el header `X-Forwarded-For` COMPLETO como identidad si está presente. La
web nunca lo mandaba —`callApi()` en `web/lib/session.ts` no reenviaba nada
propio de la request entrante—, así que todo pedido que llegaba vía la web
identificaba con el mismo REMOTE_ADDR: el contenedor de la web. Con siete
personas logueándose en un día el balde diario se vaciaba para el sitio
entero.

El arreglo tiene dos mitades, las dos necesarias:
  1. La web ahora reenvía `x-forwarded-for` en las dos rutas que pegan a
     endpoints con scope "auth" (`app/api/session/route.ts` y
     `app/api/session/codigo/route.ts` — ver sus tests en `web/tests/`).
  2. `NUM_PROXIES=1` acá, para que el backend confíe en la ÚLTIMA entrada de
     esa cabecera (la que agrega el único proxy de confianza, Traefik/Coolify)
     y no en el string entero, que el visitante puede escribir a su gusto.

Este archivo prueba sólo la mitad del backend: que, con `NUM_PROXIES=1`, dos
"visitantes" reenviados con IPs distintas no comparten balde, que el mismo
visitante sí lo agota, y que sin ninguna cabecera el throttle sigue
funcionando (cae a REMOTE_ADDR, como antes)."""

import pytest
from django.core.cache import cache
from rest_framework.settings import api_settings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _num_proxies_uno(monkeypatch):
    """Determinístico sin importar qué tenga el `.env` de quien corre esto."""
    monkeypatch.setattr(api_settings, "NUM_PROXIES", 1)


@pytest.fixture(autouse=True)
def _balde_de_uno_por_dia(monkeypatch):
    """Un solo pedido por identidad alcanza para separar "distintos" de
    "el mismo": no hace falta un balde más grande para probar la separación."""
    monkeypatch.setattr(
        "rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES",
        {"auth": "1/day"},
    )
    cache.clear()
    yield
    cache.clear()


def _pedir(client, ip=None, email="juan@gmail.com"):
    extra = {"HTTP_X_FORWARDED_FOR": ip} if ip else {}
    return client.post(
        "/api/auth/email/codigo",
        {"email": email, "lang": "es"},
        content_type="application/json",
        **extra,
    )


def test_dos_visitantes_reenviados_con_ip_distinta_no_comparten_balde(client, resend):
    """El corazón de C1: antes de este arreglo, las dos pegaban al mismo
    balde (el REMOTE_ADDR del contenedor de la web) y la segunda daba 429."""
    primero = _pedir(client, ip="203.0.113.7", email="primero@gmail.com")
    segundo = _pedir(client, ip="198.51.100.9", email="segundo@gmail.com")

    assert primero.status_code == 202, primero.json()
    assert segundo.status_code == 202, segundo.json()


def test_el_mismo_visitante_reenviado_si_agota_su_balde(client, resend):
    """El throttle no quedó apagado: sigue frenando a quien insiste."""
    primero = _pedir(client, ip="203.0.113.7", email="primero@gmail.com")
    segundo = _pedir(client, ip="203.0.113.7", email="segundo@gmail.com")

    assert primero.status_code == 202, primero.json()
    assert segundo.status_code == 429


def test_un_atacante_no_esquiva_el_balde_mandando_un_xff_propio_como_prefijo(client, resend):
    """El caso que exige NUM_PROXIES=1 en vez de dejar el header entero como
    identidad: un cliente que manda su propio prefijo en `X-Forwarded-For`
    —lo que puede escribir cualquiera— no cambia con qué IP se lo identifica,
    porque sólo se confía en la ÚLTIMA entrada (la que agrega el proxy real).
    """
    primero = _pedir(client, ip="1.1.1.1, 203.0.113.7", email="primero@gmail.com")
    segundo = _pedir(client, ip="2.2.2.2, 203.0.113.7", email="segundo@gmail.com")

    assert primero.status_code == 202, primero.json()
    # Distinto prefijo, misma última entrada real: sigue siendo el mismo balde.
    assert segundo.status_code == 429


def test_sin_x_forwarded_for_el_throttle_sigue_andando_por_remote_addr(client, resend):
    """Una sonda directa al backend, sin pasar por la web: sin la cabecera,
    `get_ident` cae a REMOTE_ADDR — el mismo comportamiento de siempre, que
    esto no puede romper."""
    primero = _pedir(client, email="primero@gmail.com")
    segundo = _pedir(client, email="segundo@gmail.com")

    assert primero.status_code == 202, primero.json()
    assert segundo.status_code == 429
