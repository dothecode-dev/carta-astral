"""Concurrencia real sobre el ledger. Superficie de PLATA.

Hasta la auditoría del 27-jul el repo no tenía NI UN test concurrente: el
`select_for_update()` de `api/ledger.py` —el mecanismo que cierra el doble
gasto— nunca se ejercitaba. Los tests corrían serializados en una sola
conexión, donde el lock ni siquiera llega a materializarse.

Estos tests usan hilos + `transaction=True` (cada hilo abre su propia conexión,
que es la única forma de que el lock de fila exista de verdad).

Sólo corren contra Postgres (ver `requiere_postgres` abajo): en SQLite no
probarían nada. Verificado que sirven quitando el `select_for_update()` de
ledger.py — 4 de estos tests se ponen en rojo, o sea que el doble gasto se
detecta.
"""

import threading

import pytest
from django.db import connection, connections

from api import ledger
from api.exceptions import QuotaExceeded
from api.models import Account, CreditTransaction

# SQLite no sirve para esto y conviene decirlo fuerte: serializa la base entera
# (los hilos mueren con "database table is locked") e **ignora**
# `SELECT ... FOR UPDATE`, así que el lock de fila que estos tests verifican
# ni siquiera existe. Un "pasa" en SQLite sería un falso verde.
#
# Corren en CI contra Postgres 16, el mismo motor que producción. Para correrlos
# a mano: DATABASE_URL=postgres://... pytest tests/api/test_ledger_concurrencia.py
requiere_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="necesita locking de fila real (Postgres); SQLite ignora FOR UPDATE",
)


def _en_hilos(fn, veces: int):
    """Corre `fn` en `veces` hilos a la vez y devuelve (resultados, errores).

    Cada hilo cierra su conexión al terminar: sin eso, las conexiones quedan
    abiertas y el teardown de la base se cuelga.
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


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_dos_consumos_simultaneos_con_un_credito_solo_uno_gana():
    """El doble gasto: con 1 crédito, dos interpretaciones a la vez."""
    acc = Account.objects.create(free_balance=1, paid_balance=0)

    def consumir(_i):
        return ledger.charge(acc, lambda: None)

    resultados, errores = _en_hilos(consumir, 2)

    assert len(resultados) == 1, "los dos consumos pasaron: doble gasto"
    assert len(errores) == 1
    assert isinstance(errores[0], QuotaExceeded)

    acc.refresh_from_db()
    assert acc.free_balance == 0
    assert acc.paid_balance == 0  # nunca queda negativo por consumo
    assert CreditTransaction.objects.filter(account=acc, kind="consumption").count() == 1


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_cinco_consumos_simultaneos_con_tres_creditos_gastan_exactamente_tres():
    acc = Account.objects.create(free_balance=2, paid_balance=1)

    resultados, errores = _en_hilos(lambda _i: ledger.charge(acc, lambda: None), 5)

    assert len(resultados) == 3
    assert all(isinstance(e, QuotaExceeded) for e in errores)

    acc.refresh_from_db()
    assert ledger.credits_available(acc) == 0
    assert CreditTransaction.objects.filter(account=acc, kind="consumption").count() == 3


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_el_mismo_evento_de_pago_en_paralelo_acredita_una_sola_vez():
    """Idempotencia del webhook bajo concurrencia real.

    RevenueCat reintenta si no recibe el 200 a tiempo: dos entregas del MISMO
    evento pueden llegar a la vez. La `UniqueConstraint` parcial sobre
    `external_id` tiene que dejar pasar una sola.
    """
    acc = Account.objects.create(free_balance=0, paid_balance=0)

    resultados, errores = _en_hilos(
        lambda _i: ledger.credit_purchase(acc, 10, external_id="evt_paralelo"), 4
    )

    assert not errores, f"un error inesperado rompió la idempotencia: {errores}"
    assert resultados.count(True) == 1, "acreditó más de una vez el mismo evento"
    assert resultados.count(False) == 3

    acc.refresh_from_db()
    assert acc.paid_balance == 10  # 10, no 40
    assert CreditTransaction.objects.filter(external_id="evt_paralelo").count() == 1


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_reembolsos_duplicados_en_paralelo_descuentan_una_sola_vez():
    acc = Account.objects.create(free_balance=0, paid_balance=10)

    resultados, errores = _en_hilos(
        lambda _i: ledger.refund_credits(acc, 10, external_id="rf_paralelo"), 3
    )

    assert not errores
    assert resultados.count(True) == 1

    acc.refresh_from_db()
    assert acc.paid_balance == 0  # no -20
    assert acc.refund_count == 1


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_acreditaciones_distintas_en_paralelo_suman_todas():
    """El contrapunto: eventos DISTINTOS no deben perderse por el lock."""
    acc = Account.objects.create(free_balance=0, paid_balance=0)

    resultados, errores = _en_hilos(
        lambda i: ledger.credit_purchase(acc, 5, external_id=f"evt_{i}"), 4
    )

    assert not errores
    assert resultados.count(True) == 4

    acc.refresh_from_db()
    assert acc.paid_balance == 20


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_consumir_y_acreditar_a_la_vez_no_pierde_ninguna_operacion():
    """Compra y consumo simultáneos sobre la misma cuenta: el saldo cierra."""
    acc = Account.objects.create(free_balance=1, paid_balance=0)

    def operar(i):
        if i % 2 == 0:
            return ledger.credit_purchase(acc, 3, external_id=f"mix_{i}")
        return ledger.charge(acc, lambda: None)

    _resultados, errores = _en_hilos(operar, 4)

    assert not [e for e in errores if not isinstance(e, QuotaExceeded)]

    acc.refresh_from_db()
    consumos = CreditTransaction.objects.filter(account=acc, kind="consumption").count()
    compras = CreditTransaction.objects.filter(account=acc, kind="purchase").aggregate(
        total=__import__("django.db.models", fromlist=["Sum"]).Sum("amount")
    )["total"] or 0
    # Invariante dura: el saldo es exactamente lo acreditado menos lo consumido.
    assert ledger.credits_available(acc) == 1 + compras - consumos


@pytest.mark.django_db
def test_la_restriccion_de_external_id_existe_en_el_motor_real():
    """La idempotencia se apoya en un índice parcial de la BASE, no en Python.

    Su semántica difiere entre SQLite y Postgres, así que este test corre en CI
    contra el motor real. Sin la restricción, dos filas con el mismo
    external_id entran y el webhook acredita dos veces.
    """
    acc = Account.objects.create()
    CreditTransaction.objects.create(
        account=acc, kind="purchase", lot="paid", amount=1, external_id="dup"
    )

    from django.db import IntegrityError

    with pytest.raises(IntegrityError):
        CreditTransaction.objects.create(
            account=acc, kind="purchase", lot="paid", amount=1, external_id="dup"
        )

    connection.close()
