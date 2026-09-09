"""C3 (Critical): la misma dirección en otro casing no crea una segunda cuenta.

`accounts.py` guardaba `vid.email` tal cual llegaba y matcheaba con un filtro
exacto sobre un `EmailField`. En SQLite el `LIKE`/`=` de texto es
case-insensitive por default, así que este bug pasaba desapercibido ahí: en
Postgres (el motor real, ver CLAUDE.md) `Juan@Gmail.com` y `juan@gmail.com`
no matcheaban, así que la persona que entraba por Google con el casing que
Google le mandó (gmail.com normaliza a minúsculas, pero un dominio Workspace
no) y después volvía por mail terminaba con una segunda cuenta y un segundo
regalo de bienvenida. Corre a propósito contra Postgres: `make test-back-pg`.
"""

import logging

import pytest

from api.accounts import resolve_account
from api.models import Account, Movimiento, ProviderIdentity
from api.sso import VerifiedIdentity

pytestmark = pytest.mark.django_db


def identidad_mail(email):
    return VerifiedIdentity(provider="email", sub=email, email=email, email_verified=True)


def identidad_google(email, sub="sub-de-google"):
    return VerifiedIdentity(provider="google", sub=sub, email=email, email_verified=True)


def test_google_con_mayusculas_y_mail_en_minusculas_caen_en_la_misma_cuenta():
    """El caso medido por el revisor: Workspace le manda el claim con casing
    mixto a Google, la persona después entra por mail en minúsculas."""
    por_google = resolve_account(identidad_google("Juan@Gmail.com"))
    por_mail = resolve_account(identidad_mail("juan@gmail.com"))

    assert por_mail.pk == por_google.pk
    assert Account.objects.count() == 1
    assert Movimiento.objects.filter(account=por_google, origen="regalo").count() == 1


def test_mail_en_minusculas_primero_y_google_con_mayusculas_despues_caen_en_la_misma_cuenta():
    """El caso inverso: se registra por mail y vuelve por Google con otro casing."""
    por_mail = resolve_account(identidad_mail("juan@gmail.com"))
    por_google = resolve_account(identidad_google("Juan@Gmail.com"))

    assert por_mail.pk == por_google.pk
    assert Account.objects.count() == 1
    assert Movimiento.objects.filter(account=por_mail, origen="regalo").count() == 1


def test_cuentas_duplicadas_preexistentes_no_generan_una_tercera_y_dejan_warning(caplog):
    """El estado que ya puede existir hoy en producción: dos cuentas verificadas
    con la misma dirección en casing distinto. Antes del fix, `resolve_account`
    entraba por una tercera identidad y salía una TERCERA cuenta, sin loguear
    nada. El arreglo linkea a una de las dos existentes (nunca crea una
    tercera) y deja un warning con los pks para que alguien lo limpie a mano —
    mezclar los datos de las dos cuentas no es una decisión que este código
    pueda tomar solo."""
    una = Account.objects.create(email="Juan@Gmail.com", email_verified=True)
    otra = Account.objects.create(email="juan@gmail.com", email_verified=True)

    with caplog.at_level(logging.WARNING, logger="api.accounts"):
        resultado = resolve_account(identidad_google("juan@gmail.com", sub="tercera-identidad"))

    assert Account.objects.count() == 2
    assert resultado.pk in {una.pk, otra.pk}
    assert ProviderIdentity.objects.filter(account=resultado).count() == 1

    mensajes = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(str(una.pk) in m and str(otra.pk) in m for m in mensajes)
    # Ninguna direccion completa en el log: solo pks.
    assert not any("juan@gmail.com" in m.lower() for m in mensajes)
