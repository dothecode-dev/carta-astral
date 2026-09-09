import pytest

from api.accounts import resolve_account
from api.codigos_acceso import canjear, pedir
from api.models import Account, Derecho, Movimiento, ProviderIdentity
from api.sso import VerifiedIdentity

pytestmark = pytest.mark.django_db


def identidad_mail(email):
    return VerifiedIdentity(
        provider="email", sub=email, email=email, email_verified=True,
    )


def test_una_direccion_nueva_nace_con_el_regalo():
    cuenta = resolve_account(identidad_mail("juan@gmail.com"))
    derecho = Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve")
    assert derecho.cantidad_restante == 3


def test_dos_canjes_seguidos_no_regalan_el_doble():
    """Lo garantiza el match temprano por `ProviderIdentity(provider, sub)`
    en `resolve_account()` (accounts.py:44-46): la segunda llamada devuelve
    la cuenta ya linkeada y nunca vuelve a entrar a `_create_account()` ni a
    `otorgar_bienvenida()`. El `external_id` determinístico `bienvenida:{pk}`
    de `otorgar_bienvenida()` cubre otro caso, el de la carrera concurrente
    (dos resoluciones del mismo sub nuevo en paralelo), que ya prueba
    `test_concurrent_create_of_same_new_sub_does_not_duplicate` en
    `test_account_resolution.py`."""
    cuenta = resolve_account(identidad_mail("juan@gmail.com"))
    otra = resolve_account(identidad_mail("juan@gmail.com"))
    assert cuenta.pk == otra.pk
    assert Movimiento.objects.filter(account=cuenta, origen="regalo").count() == 1


def test_quien_entro_por_google_cae_en_la_misma_cuenta_al_entrar_por_mail():
    """El caso que más va a pasar: se registró con Google y vuelve por mail."""
    por_google = resolve_account(VerifiedIdentity(
        provider="google", sub="sub-de-google", email="juan@gmail.com",
        email_verified=True,
    ))
    por_mail = resolve_account(identidad_mail("juan@gmail.com"))
    assert por_mail.pk == por_google.pk
    assert Movimiento.objects.filter(account=por_google, origen="regalo").count() == 1
    assert ProviderIdentity.objects.filter(account=por_google).count() == 2


def test_la_direccion_se_normaliza_antes_de_resolver():
    """No simula la normalización en un helper del test: entra por el camino
    real de producción. `pedir()` normaliza al crear la fila
    (codigos_acceso.py:74) y `canjear()` normaliza al arrancar
    (codigos_acceso.py:146), así que `fila.email` ya sale normalizado — es
    ESE valor, y no el string crudo del pedido, el que tiene que usar quien
    arme la `VerifiedIdentity` (la vista de la tarea 7). Cada llamada pide y
    canjea un código nuevo: como `canjear()` marca `usado_en` en la fila, la
    segunda `pedir()` no encuentra una fila vigente para reenviar y crea una
    propia — dos pedidos sobre la misma dirección, muy por debajo del techo
    de 5 envíos/hora.
    """
    def entrar_por_mail(email: str) -> Account:
        _fila, claro, _reenvio = pedir(email)
        canjeada = canjear(email, claro)
        return resolve_account(VerifiedIdentity(
            provider="email", sub=canjeada.email, email=canjeada.email,
            email_verified=True,
        ))

    primera = entrar_por_mail("juan@gmail.com")
    segunda = entrar_por_mail("Juan@Gmail.com")
    assert primera.pk == segunda.pk
    assert Account.objects.count() == 1
