"""Concurrencia real sobre el pedido y el canje del código de acceso por mail.

El primer test cubre `pedir()`: dos pedidos casi a la vez (doble clic) para
una dirección SIN código vigente. `select_for_update()` no bloquea nada
cuando todavía no existe fila que lockear: los dos hilos pasan el
`select_for_update` con `fila=None` y los dos intentan `create()`. Postgres
deja pasar uno y el otro choca con la `UniqueConstraint` parcial — sin
capturarlo era un 500 pelado por un doble clic o dos pestañas (la spec lo
lista como riesgo Importante).

El segundo cubre `canjear()`, pero por el ENDPOINT HTTP y con dos `Client`
propios — "dos pestañas" es HTTP, no una llamada directa al servicio —: dos
canjes del mismo código a la vez tienen que dejar una sola sesión válida, una
sola cuenta y un solo regalo de bienvenida. Acá si SÍ hay fila que lockear
(el código ya existe), así que el `select_for_update()` de `canjear()` es lo
que evita que los dos hilos lean `usado_en IS NULL` a la vez y los dos pasen.

Sólo corren contra Postgres (ver `tests/api/concurrencia.py`): en SQLite
`SELECT ... FOR UPDATE` se ignora y el escenario ni siquiera se da.
"""
import pytest
from django.db import connection
from django.test import Client

from api import codigos_acceso
from api.models import Account, CodigoAcceso, Movimiento
from tests.api.concurrencia import en_hilos, requiere_postgres

pytestmark = [pytest.mark.django_db(transaction=True), requiere_postgres]


def test_dos_pedidos_casi_a_la_vez_sin_codigo_previo_no_revientan():
    def pedir(_i):
        try:
            return codigos_acceso.pedir("juan@gmail.com")
        finally:
            connection.close()

    resultados, errores = en_hilos(pedir, 2)

    assert errores == [], f"no debería propagar nada: {errores!r}"
    assert len(resultados) == 2
    # Una sola fila sobrevive: la que ganó la carrera del create() más el
    # reenvío en el que se degradó el segundo hilo.
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 1
    fila = CodigoAcceso.objects.get(email="juan@gmail.com")
    # El segundo hilo se degrada a reenvío sobre la misma fila que ganó.
    assert {r[0].pk for r in resultados} == {fila.pk}
    assert sorted(r[2] for r in resultados) == [False, True]
    # Dos mails salieron (uno por hilo), así que el techo tiene que reflejarlo.
    assert fila.envios == 2


def test_dos_pestanas_canjeando_el_mismo_codigo_por_http_dejan_una_sola_cuenta_y_un_solo_regalo():
    _, claro, _ = codigos_acceso.pedir("juan@gmail.com")

    def canjear(_i):
        # Un `Client` propio por hilo: compartir uno entre hilos mezclaría
        # sesiones y no simula dos pestañas de verdad.
        cliente = Client()
        try:
            return cliente.post(
                "/api/auth/email",
                {"email": "juan@gmail.com", "codigo": claro},
                content_type="application/json",
            )
        finally:
            connection.close()

    respuestas, errores = en_hilos(canjear, veces=2)

    assert errores == [], f"no debería propagar nada: {errores!r}"
    assert sorted(r.status_code for r in respuestas) == [200, 401]
    assert Account.objects.filter(email="juan@gmail.com").count() == 1
    assert Movimiento.objects.filter(origen="regalo").count() == 1
