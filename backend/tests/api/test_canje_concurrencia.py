"""Concurrencia real sobre el canje. Superficie de PLATA.

Sin `select_for_update()` en `canjear()`, dos canjes simultáneos con un solo
derecho dejan dos consumos (doble gasto); sin la `UniqueConstraint` parcial de
`Movimiento.external_id`, dos entregas del mismo evento de pago acreditan dos
veces. Estos tests usan hilos + `transaction=True` (cada hilo abre su propia
conexión, que es la única forma de que el lock de fila exista de verdad).

Heredaron la cobertura de `test_ledger_concurrencia.py`, que murió con el
ledger viejo: los cinco escenarios de plata que aquel archivo ejercía sobre
`charge`/`credit_purchase`/`refund_credits` están acá sobre
`canjear`/`otorgar`/`revocar`, que son quienes mueven la plata hoy.

Sólo corren contra Postgres (ver `requiere_postgres` abajo): en SQLite
`SELECT ... FOR UPDATE` se ignora y no probarían nada. Verificado que sirve
quitando el `select_for_update()` de `canje.py`: los tests se ponen en rojo
con dos consumos en vez de uno.
"""

import threading

import pytest
from django.db import connection, connections
from django.db.models import Sum

from api.canje import SinDerecho, canjear, otorgar, revocar
from api.models import Derecho, Movimiento

# SQLite serializa la base entera e ignora `SELECT ... FOR UPDATE`, así que el
# lock de fila que estos tests verifican ni siquiera existe ahí: un "pasa" en
# SQLite sería un falso verde. Corre en CI contra Postgres 16; a mano:
# `make staging-up && make test-back-pg`.
requiere_postgres = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="necesita locking de fila real (Postgres); SQLite ignora FOR UPDATE",
)


def _en_hilos(fn, veces: int):
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


def _restante(codigo="informe_natal") -> int:
    return Derecho.objects.get(codigo_producto=codigo).cantidad_restante


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


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_cinco_canjes_simultaneos_con_tres_derechos_gastan_exactamente_tres(
    make_account, make_chart,
):
    """El lock de fila cierra el doble gasto también con más de un derecho en
    juego, no sólo con uno (arriba). Cinco cartas distintas: `canjear` es un
    no-op cuando la carta ya tiene esa capacidad canjeada, así que repetir la
    misma carta mediría el no-op y no la carrera."""
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 3, origen="compra", external_id="p:3")
    cartas = [make_chart(account=cuenta) for _ in range(5)]

    resultados, errores = _en_hilos(lambda i: canjear(cuenta, "leer_informe", cartas[i]), 5)

    assert len(resultados) == 3
    assert all(isinstance(e, SinDerecho) for e in errores)
    assert _restante() == 0
    assert Movimiento.objects.filter(tipo="consumo").count() == 3


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_el_mismo_evento_de_pago_en_paralelo_otorga_una_sola_vez(make_account):
    """Idempotencia del webhook bajo concurrencia real.

    La pasarela reintenta si no recibe el 200 a tiempo: dos entregas del MISMO
    evento pueden llegar a la vez. La `UniqueConstraint` parcial sobre
    `Movimiento.external_id` tiene que dejar pasar una sola.
    """
    cuenta = make_account()

    resultados, errores = _en_hilos(
        lambda _i: otorgar(
            cuenta, "informe_natal", 10, origen="compra", external_id="evt_paralelo",
        ),
        4,
    )

    assert not errores, f"un error inesperado rompió la idempotencia: {errores}"
    assert resultados.count(True) == 1, "acreditó más de una vez el mismo evento"
    assert resultados.count(False) == 3
    assert _restante() == 10  # 10, no 40
    assert Movimiento.objects.filter(external_id="evt_paralelo").count() == 1


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_otorgamientos_distintos_en_paralelo_suman_todos(make_account):
    """El contrapunto: eventos DISTINTOS no deben perderse por el lock."""
    cuenta = make_account()

    resultados, errores = _en_hilos(
        lambda i: otorgar(
            cuenta, "informe_natal", 5, origen="compra", external_id=f"evt_{i}",
        ),
        4,
    )

    assert not errores
    assert resultados.count(True) == 4
    assert _restante() == 20


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_revocaciones_duplicadas_en_paralelo_descuentan_una_sola_vez(make_account):
    """Un chargeback reintentado no puede cobrarse dos veces: descuenta un solo
    derecho y suma un solo `refund_count` (que es lo que puede terminar
    marcando la cuenta para revisión manual)."""
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 10, origen="compra", external_id="p:rev")

    resultados, errores = _en_hilos(
        lambda _i: revocar(cuenta, "informe_natal", 10, external_id="rf_paralelo"), 3,
    )

    assert not errores
    assert resultados.count(True) == 1
    assert _restante() == 0  # no queda en -20 ni se revoca dos veces
    cuenta.refresh_from_db()
    assert cuenta.refund_count == 1
    assert cuenta.deuda == 0


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_canjear_y_otorgar_a_la_vez_no_pierde_ninguna_operacion(make_account, make_chart):
    """Compra y consumo simultáneos sobre la misma cuenta: el saldo cierra.

    El invariante duro del libro (`Movimiento`): lo que le queda al derecho es
    exactamente la suma firmada de sus movimientos.
    """
    cuenta = make_account()
    otorgar(cuenta, "informe_natal", 1, origen="compra", external_id="p:mix")
    cartas = [make_chart(account=cuenta) for _ in range(4)]

    def operar(i):
        if i % 2 == 0:
            return otorgar(
                cuenta, "informe_natal", 3, origen="compra", external_id=f"mix_{i}",
            )
        return canjear(cuenta, "leer_informe", cartas[i])

    _resultados, errores = _en_hilos(operar, 4)

    assert not [e for e in errores if not isinstance(e, SinDerecho)]
    movido = Movimiento.objects.filter(codigo_producto="informe_natal").aggregate(
        total=Sum("cantidad"),
    )["total"]
    assert _restante() == movido
