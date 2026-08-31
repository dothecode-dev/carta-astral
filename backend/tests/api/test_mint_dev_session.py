import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_crea_la_cuenta_con_derecho_de_lectura_breve(settings):
    settings.DEBUG = True
    from api.models import Account, Derecho

    call_command("mint_dev_session", "--credits", "7")

    acc = Account.objects.get(email="dev@localhost")
    assert Derecho.objects.get(account=acc, codigo_producto="lectura_breve").cantidad_restante == 7


@pytest.mark.django_db
def test_reutilizar_la_cuenta_no_vuelve_a_otorgar(settings):
    settings.DEBUG = True
    from api.models import Account, Derecho

    call_command("mint_dev_session", "--credits", "7")
    call_command("mint_dev_session", "--credits", "3")  # segunda corrida, misma cuenta

    acc = Account.objects.get(email="dev@localhost")
    assert Derecho.objects.get(account=acc, codigo_producto="lectura_breve").cantidad_restante == 7


@pytest.mark.django_db
def test_se_niega_a_correr_sin_debug(settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("mint_dev_session")
