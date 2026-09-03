"""Herramientas para los tests de concurrencia real (hilos + Postgres).

Viven acá porque las comparten los del canje y los del webhook de Stripe, y
duplicarlas era garantizar que un día se arreglen en un archivo y no en el otro.
"""

import threading

import pytest
from django.db import connection, connections

# SQLite serializa la base entera e ignora `SELECT ... FOR UPDATE`, así que el
# lock de fila que estos tests verifican ni siquiera existe ahí: un "pasa" en
# SQLite sería un falso verde. Corre en CI contra Postgres 16; a mano:
# `make staging-up && make test-back-pg`.
requiere_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="necesita locking de fila real (Postgres); SQLite ignora FOR UPDATE",
)


def en_hilos(fn, veces: int):
    """Corre `fn(i)` en `veces` hilos a la vez y devuelve (resultados, errores).

    Cada hilo cierra su conexión al terminar: sin eso quedan abiertas y el
    teardown de la base se cuelga.
    """
    resultados, errores = [], []
    barrera = threading.Barrier(veces)

    def worker(i):
        try:
            barrera.wait()  # todos arrancan lo más juntos posible
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
