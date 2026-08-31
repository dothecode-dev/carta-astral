"""Migración de datos `0024_migrar_balances_a_derechos`.

Los dos contadores viejos (`free_balance`, `paid_balance`) pasan a derechos
nombrados por producto. Sin esta migración, desplegar el modelo de canje le
devuelve 402 a TODAS las cuentas que ya existen: tienen saldo en los campos
viejos y cero derechos, y `canje.puede()` sólo mira derechos.

Se prueba con el patrón de `test_backfill_completa.py` —importar la función de
la migración y correrla contra el registro real de modelos—: en este repo no
está `django_test_migrations`, y en la 0024 los tres modelos que toca
(`Account`, `Derecho`, `Movimiento`) ya existen en el estado actual, así que
el registro real alcanza.
"""

import importlib
import logging

import pytest
from django.apps import apps as django_apps
from django.test import override_settings

from api.models import Account, Derecho, Movimiento, ProviderIdentity, SubTombstone

pytestmark = pytest.mark.django_db

_migracion = importlib.import_module("api.migrations.0024_migrar_balances_a_derechos")


def _migrar():
    _migracion.migrar(django_apps, None)


def _revertir():
    _migracion.revertir(django_apps, None)


def _derecho(cuenta, codigo):
    return Derecho.objects.get(account=cuenta, codigo_producto=codigo)


def test_el_saldo_gratis_y_el_pago_se_convierten_en_derechos():
    cuenta = Account.objects.create(email="x@y.z", free_balance=2, paid_balance=1)

    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 2
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 1
    cuenta.refresh_from_db()
    assert cuenta.deuda == 0


def test_un_saldo_pago_negativo_se_convierte_en_deuda():
    """`paid_balance` es signed: el clawback de un reembolso lo dejaba
    negativo. En el modelo nuevo eso no cabe en `cantidad_restante` (es
    Positive), y va a `Account.deuda`, que es donde el canje ya la busca."""
    cuenta = Account.objects.create(email="d@y.z", free_balance=0, paid_balance=-2)

    _migrar()

    assert _derecho(cuenta, "informe_natal").cantidad_restante == 0
    cuenta.refresh_from_db()
    assert cuenta.deuda == 2


def test_deja_un_movimiento_de_ajuste_por_cada_derecho():
    cuenta = Account.objects.create(email="m@y.z", free_balance=3, paid_balance=5)

    _migrar()

    movs = {m.codigo_producto: m for m in Movimiento.objects.filter(account=cuenta)}
    assert set(movs) == {"lectura_breve", "informe_natal"}
    for codigo, mov in movs.items():
        assert mov.tipo == "otorgamiento"
        assert mov.origen == "ajuste"
        assert mov.external_id == f"migracion:0024:{cuenta.pk}:{codigo}"
    assert movs["lectura_breve"].cantidad == 3
    assert movs["informe_natal"].cantidad == 5


def test_es_idempotente():
    """El `external_id` es único GLOBAL: si la segunda corrida volviera a
    insertar el movimiento, esto reventaría con IntegrityError en vez de
    fallar en el assert."""
    cuenta = Account.objects.create(email="i@y.z", free_balance=2, paid_balance=1)

    _migrar()
    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 2
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 1
    assert Movimiento.objects.filter(account=cuenta).count() == 2


def test_no_pisa_un_derecho_que_ya_existia():
    """Una cuenta creada con el código nuevo (alta con `otorgar_bienvenida`)
    ya tiene su derecho antes de que corra la migración: sumarle otra vez el
    `free_balance` sería regalar el doble."""
    cuenta = Account.objects.create(email="p@y.z", free_balance=3, paid_balance=0)
    Derecho.objects.create(account=cuenta, codigo_producto="lectura_breve", cantidad_restante=3)

    _migrar()

    assert _derecho(cuenta, "lectura_breve").cantidad_restante == 3
    assert Movimiento.objects.filter(
        account=cuenta, codigo_producto="lectura_breve",
    ).count() == 0


def test_avisa_por_log_del_saldo_que_descarta(caplog):
    """El descarte tiene que dejar rastro: la migración corre UNA vez contra
    datos reales y no se puede re-correr para averiguar qué se perdió. En
    `informe_natal` el número descartado es plata."""
    cuenta = Account.objects.create(email="log@y.z", free_balance=0, paid_balance=4)
    Derecho.objects.create(account=cuenta, codigo_producto="informe_natal", cantidad_restante=1)

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _migrar()

    assert [r.getMessage() for r in caplog.records] == [
        f"0024: la cuenta {cuenta.pk} ya tenía derecho de informe_natal; "
        f"se descarta el saldo viejo de 4",
    ]


def test_no_avisa_cuando_no_hay_saldo_que_descartar(caplog):
    """Contrapunto: el derecho de `lectura_breve` en cero de una cuenta ya
    migrada no descarta nada, y un warning por cada cuenta y cada producto
    ahogaría al que sí importa."""
    cuenta = Account.objects.create(email="nolog@y.z", free_balance=0, paid_balance=0)
    Derecho.objects.create(account=cuenta, codigo_producto="lectura_breve", cantidad_restante=0)

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _migrar()

    assert caplog.records == []


def test_no_pisa_una_deuda_que_el_canje_ya_habia_anotado():
    """La guarda `if deuda and not cuenta.deuda`.

    Si la cuenta ya debe algo, esa deuda la anotó el código nuevo (`revocar`)
    y es la que sostiene el cobro de hoy: la del `paid_balance` negativo del
    ledger viejo se descarta. El desvío que eso acepta está anotado en la
    migración: la reversa devuelve `-1`, no el `-3` que sumaría las dos.
    """
    cuenta = Account.objects.create(email="deu@y.z", free_balance=0, paid_balance=-2)
    Account.objects.filter(pk=cuenta.pk).update(deuda=1)

    _migrar()

    cuenta.refresh_from_db()
    assert cuenta.deuda == 1
    assert _derecho(cuenta, "informe_natal").cantidad_restante == 0

    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.paid_balance == -1  # desvío conocido y documentado, no un bug nuevo
    assert cuenta.deuda == 0


def test_la_reversa_reconstruye_los_saldos_desde_los_derechos():
    cuenta = Account.objects.create(email="r@y.z", free_balance=2, paid_balance=4)

    _migrar()
    Account.objects.filter(pk=cuenta.pk).update(free_balance=0, paid_balance=0)
    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.free_balance == 2
    assert cuenta.paid_balance == 4
    assert cuenta.deuda == 0


def test_la_reversa_devuelve_la_deuda_como_saldo_negativo():
    cuenta = Account.objects.create(email="rd@y.z", free_balance=1, paid_balance=-3)

    _migrar()
    _revertir()

    cuenta.refresh_from_db()
    assert cuenta.free_balance == 1
    assert cuenta.paid_balance == -3
    assert cuenta.deuda == 0


@override_settings(INSTALL_FREE_CREDITS=3)
def test_borrar_una_cuenta_migrada_deja_el_tombstone_correcto():
    """El puente entre la migración y el anti-abuso de `deletion.py`.

    Una cuenta migrada NO tiene movimientos de consumo: gastó 2 de sus 3
    lecturas gratis con el ledger viejo y la migración sólo ve el saldo que
    quedó (1). Si el tombstone se calculara contando movimientos de consumo,
    diría 0 y el usuario podría borrar la cuenta y volver a entrar para
    recibir otras 3 lecturas gratis.
    """
    from api.deletion import delete_account
    from api.identity import sub_hash

    cuenta = Account.objects.create(email="t@y.z", free_balance=1, paid_balance=0)
    ProviderIdentity.objects.create(provider="apple", sub="MIGRADA", account=cuenta)

    _migrar()
    delete_account(cuenta)

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "MIGRADA"))
    assert tomb.free_credits_consumed == 2
