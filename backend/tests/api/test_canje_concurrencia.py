"""Concurrencia real sobre el canje. Superficie de PLATA.

Mismo motivo que `test_ledger_concurrencia.py`: sin `select_for_update()` en
`canjear()`, dos canjes simultáneos con un solo derecho podrían dejar dos
consumos (doble gasto). Este test usa hilos + `transaction=True` (cada hilo
abre su propia conexión, que es la única forma de que el lock de fila exista
de verdad).

Sólo corre contra Postgres (ver `requiere_postgres` abajo): en SQLite
`SELECT ... FOR UPDATE` se ignora y el test no probaría nada. Verificado que
sirve quitando el `select_for_update()` de `canje.py`: el test se pone en
rojo con dos consumos en vez de uno.
"""

import threading

import pytest
from django.db import connection

from api.canje import SinDerecho, canjear, otorgar
from api.models import Derecho, Movimiento

# Mismo motivo que en test_ledger_concurrencia.py: SQLite serializa la base
# entera e ignora `SELECT ... FOR UPDATE`, así que el lock de fila que este
# test verifica ni siquiera existe ahí. Corre en CI contra Postgres 16; a
# mano: `make staging-up && make test-back-pg`.
requiere_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="necesita locking de fila real (Postgres); SQLite ignora FOR UPDATE",
)


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_dos_canjes_simultaneos_con_un_solo_derecho_dejan_uno_solo(make_account, make_chart):
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:1")
    cartas = [make_chart(account=cuenta), make_chart(account=cuenta)]
    errores, listo = [], threading.Barrier(2)

    def correr(carta):
        listo.wait()
        try:
            canjear(cuenta, "leer_informe", carta)
        except SinDerecho as e:
            errores.append(e)
        finally:
            connection.close()

    hilos = [threading.Thread(target=correr, args=(c,)) for c in cartas]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)

    assert len(errores) == 1
    assert Derecho.objects.get(codigo_producto="informe_natal").cantidad_restante == 0
    assert Movimiento.objects.filter(tipo="consumo").count() == 1
