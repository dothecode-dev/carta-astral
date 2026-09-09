"""Migración `0035_normalizar_casing_de_cuentas` (C3, revisión de
`puertas-de-acceso`): normaliza a minúsculas el `email` de las `Account` que
ya estaban guardadas con casing mixto de antes del fix de `accounts.py`.

No fusiona cuentas duplicadas —eso queda para revisión manual, ver el
docstring de la migración— así que estos tests verifican sólo lo que sí
hace: normalizar y avisar.
"""

import importlib
import logging

import pytest
from django.apps import apps as django_apps

from api.models import Account

pytestmark = pytest.mark.django_db

_migracion = importlib.import_module("api.migrations.0035_normalizar_casing_de_cuentas")


def _correr():
    _migracion.normalizar_casing(django_apps, None)


def test_normaliza_el_casing_mixto():
    cuenta = Account.objects.create(email="Juan@Gmail.com", email_verified=True)

    _correr()

    cuenta.refresh_from_db()
    assert cuenta.email == "juan@gmail.com"


def test_no_toca_una_cuenta_ya_normalizada():
    cuenta = Account.objects.create(email="juan@gmail.com", email_verified=True)

    _correr()

    cuenta.refresh_from_db()
    assert cuenta.email == "juan@gmail.com"


def test_no_toca_una_cuenta_sin_email():
    cuenta = Account.objects.create(email="", email_verified=False)

    _correr()  # no debe reventar

    cuenta.refresh_from_db()
    assert cuenta.email == ""


def test_avisa_de_las_cuentas_que_quedan_duplicadas_tras_normalizar(caplog):
    """No las fusiona: sólo deja rastro en el log, con pks y sin la dirección,
    para que se revisen a mano."""
    una = Account.objects.create(email="Juan@Gmail.com", email_verified=True)
    otra = Account.objects.create(email="juan@gmail.com", email_verified=True)

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _correr()

    assert Account.objects.count() == 2  # no se fusionan
    mensajes = [r.getMessage() for r in caplog.records]
    assert any(str(una.pk) in m and str(otra.pk) in m for m in mensajes)
    assert not any("juan@gmail.com" in m.lower() for m in mensajes)


def test_no_avisa_cuando_no_hay_duplicados(caplog):
    Account.objects.create(email="unica@gmail.com", email_verified=True)

    with caplog.at_level(logging.WARNING, logger=_migracion.__name__):
        _correr()

    assert caplog.records == []


def test_es_idempotente():
    cuenta = Account.objects.create(email="Juan@Gmail.com", email_verified=True)

    _correr()
    _correr()

    cuenta.refresh_from_db()
    assert cuenta.email == "juan@gmail.com"
