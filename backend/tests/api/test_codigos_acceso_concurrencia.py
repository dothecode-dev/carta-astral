"""Concurrencia real sobre el pedido y el canje del código de acceso por mail.

El primer test cubre `pedir()`: dos pedidos casi a la vez (doble clic) para
una dirección SIN código vigente. Antes de Hallazgo I1 esto necesitaba un
savepoint y capturar `IntegrityError` porque una `UniqueConstraint` parcial
permitía sólo un código vigente por dirección, y Postgres dejaba pasar un
`create()` y hacía chocar el otro. Esa constraint se sacó: ahora conviven
varios códigos vigentes por dirección, así que dos pedidos a la vez
simplemente crean dos filas independientes, sin ningún choque que capturar.
El test queda igual como regresión — que un doble clic no reviente— aunque ya
no dependa de locking real de Postgres.

El segundo cubre `canjear()`, pero por el ENDPOINT HTTP y con dos `Client`
propios — "dos pestañas" es HTTP, no una llamada directa al servicio —: dos
canjes del mismo código a la vez tienen que dejar una sola sesión válida, una
sola cuenta y un solo regalo de bienvenida. Acá sí hay fila que lockear (el
código ya existe), así que el `select_for_update()` de `canjear()` sobre las
filas vigentes de la dirección es lo que evita que los dos hilos lean
`usado_en IS NULL` a la vez y los dos pasen — mismo mecanismo que antes,
ahora sobre una lista de filas en vez de una sola.

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
    # Sin constraint que impida convivir, los dos hilos crean su propia fila:
    # no hay carrera que perder ni degradación a reenvío.
    assert CodigoAcceso.objects.filter(email="juan@gmail.com").count() == 2
    pks = {r[0].pk for r in resultados}
    assert len(pks) == 2
    codigos = {r[1] for r in resultados}
    assert len(codigos) == 2
    # El tercer valor (¿había uno vigente antes?) no se afirma acá: es una
    # lectura sin lock (a propósito, ver el comentario de `pedir()`), así que
    # cuál de los dos hilos "ve" al otro primero no está definido.


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
