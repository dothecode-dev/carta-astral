import itertools

import pytest
from django.test import override_settings

from api.canje import puede
from api.models import Derecho, Movimiento
from api.sso import VerifiedIdentity

pytestmark = pytest.mark.django_db

_contador = itertools.count()


@pytest.fixture
def crear_cuenta():
    """Crea una cuenta por el camino real del alta: `resolve_account` con una
    identidad SSO verificada nueva, igual que un login real de Apple/Google.

    Cada llamado usa un `sub` distinto para no pisar la cuenta anterior.
    """
    from api.accounts import resolve_account

    def _crear_cuenta():
        n = next(_contador)
        vid = VerifiedIdentity(
            provider="apple", sub=f"sub-{n}", email=f"user{n}@x.com", email_verified=True,
        )
        return resolve_account(vid)

    return _crear_cuenta


@override_settings(INSTALL_FREE_CREDITS=3)
def test_una_cuenta_nueva_arranca_con_tres_lecturas_breves(crear_cuenta):
    cuenta = crear_cuenta()

    d = Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve")
    assert d.cantidad_restante == 3
    assert Movimiento.objects.get(account=cuenta).origen == "regalo"
    assert puede(cuenta, "leer_breve") is True


@override_settings(INSTALL_FREE_CREDITS=3)
def test_una_cuenta_nueva_no_puede_leer_un_informe(crear_cuenta):
    assert puede(crear_cuenta(), "leer_informe") is False


@override_settings(INSTALL_FREE_CREDITS=3)
def test_repetir_el_regalo_no_da_seis(crear_cuenta):
    # Antes el 3 era el `default` del campo y duplicarlo era imposible. Al
    # moverlo a código hace falta un external_id determinístico.
    from api.accounts import otorgar_bienvenida

    cuenta = crear_cuenta()
    otorgar_bienvenida(cuenta)

    assert Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve").cantidad_restante == 3
