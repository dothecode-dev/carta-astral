import pytest


@pytest.mark.django_db
def test_account_defaults():
    """Una cuenta recién creada no puede hacer NADA por sí sola.

    La 0025 borró los dos contadores que traían saldo en el default del
    modelo: lo que la cuenta puede hacer vive en `Derecho`, y ese derecho lo
    otorga el alta (`accounts.otorgar_bienvenida`), no el ORM. Crear una
    `Account` a secas y esperar lecturas gratis es justo el supuesto que el
    modelo de canje eliminó."""
    from api.models import Account, Derecho

    acc = Account.objects.create()
    assert not Derecho.objects.filter(account=acc).exists()
    assert acc.deuda == 0
    assert acc.email == "" or acc.email is None
    assert acc.email_verified is False
    assert acc.is_authenticated is True
    assert acc.is_anonymous is False
