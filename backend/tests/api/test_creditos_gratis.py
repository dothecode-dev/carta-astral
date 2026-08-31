import itertools

import pytest
from django.conf import settings
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

    Sin `sub` explícito, cada llamado usa uno distinto (contador incremental)
    para no pisar la cuenta anterior. Con `sub` explícito, permite armar un
    `SubTombstone` de antemano que matchee ese sub exacto.
    """
    from api.accounts import resolve_account

    def _crear_cuenta(sub=None):
        if sub is None:
            sub = f"sub-{next(_contador)}"
        vid = VerifiedIdentity(
            provider="apple", sub=sub, email=f"{sub}@x.com", email_verified=True,
        )
        return resolve_account(vid)

    return _crear_cuenta


def test_el_cap_diario_acota_el_gasto_al_costo_nuevo():
    # Un informe cuesta ~US$0,45, no ~US$0,03: con el cap viejo (500) el techo
    # de regalo pasaba de US$15 a más de US$200 por día.
    assert settings.INTERPRETATION_DAILY_CAP * 0.45 <= 20


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
    otorgar_bienvenida(cuenta, 3)

    assert Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve").cantidad_restante == 3


@override_settings(INSTALL_FREE_CREDITS=3)
def test_el_tombstone_descuenta_del_regalo(crear_cuenta):
    # Ya se gastaron 2 de las 3 lecturas gratis en un ciclo anterior (cuenta
    # borrada y re-creada con el mismo sub): el regalo nuevo tiene que dar
    # sólo lo que falta, no las 3 de nuevo.
    from api.identity import sub_hash
    from api.models import SubTombstone

    SubTombstone.objects.create(sub_hash=sub_hash("apple", "tomb-parcial"), free_credits_consumed=2)
    cuenta = crear_cuenta(sub="tomb-parcial")

    assert Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve").cantidad_restante == 1


@override_settings(INSTALL_FREE_CREDITS=3)
def test_el_tombstone_agotado_no_regala_nada(crear_cuenta):
    # Las 3 lecturas gratis ya se consumieron antes: sin esto, borrar la
    # cuenta y volver a entrar sería una forma infinita de conseguir lecturas
    # gratis.
    from api.identity import sub_hash
    from api.models import SubTombstone

    SubTombstone.objects.create(sub_hash=sub_hash("apple", "tomb-agotado"), free_credits_consumed=3)
    cuenta = crear_cuenta(sub="tomb-agotado")

    assert not Derecho.objects.filter(account=cuenta, codigo_producto="lectura_breve").exists()
    assert Movimiento.objects.filter(account=cuenta, origen="regalo").count() == 0
    assert puede(cuenta, "leer_breve") is False
