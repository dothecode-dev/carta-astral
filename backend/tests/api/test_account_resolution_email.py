import pytest

from api.accounts import resolve_account
from api.codigos_acceso import normalizar
from api.models import Account, Derecho, Movimiento, ProviderIdentity
from api.sso import VerifiedIdentity

pytestmark = pytest.mark.django_db


def identidad_mail(email):
    # Simula el borde real: quien arma la `VerifiedIdentity` a partir de un
    # `CodigoAcceso.canjear()` normaliza antes de construirla — igual que
    # `pedir()` y `canjear()` ya normalizan la dirección con la que operan.
    # `resolve_account()` no sabe de mails ni de normalización (RF2-RF5):
    # sigue siendo el mismo contrato compartido con Apple y Google.
    email = normalizar(email)
    return VerifiedIdentity(
        provider="email", sub=email, email=email, email_verified=True,
    )


def test_una_direccion_nueva_nace_con_el_regalo():
    cuenta = resolve_account(identidad_mail("juan@gmail.com"))
    derecho = Derecho.objects.get(account=cuenta, codigo_producto="lectura_breve")
    assert derecho.cantidad_restante == 3


def test_dos_canjes_seguidos_no_regalan_el_doble():
    """Lo garantiza el external_id determinístico `bienvenida:{pk}` que ya
    existe en otorgar_bienvenida()."""
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
    primera = resolve_account(identidad_mail("juan@gmail.com"))
    segunda = resolve_account(identidad_mail("Juan@Gmail.com"))
    assert primera.pk == segunda.pk
    assert Account.objects.count() == 1
