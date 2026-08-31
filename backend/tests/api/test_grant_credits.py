import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.mark.django_db
def test_grant_credits_otorga_derecho_de_informe_natal():
    from api.models import Account, Derecho

    acc = Account.objects.create()
    call_command("grant_credits", str(acc.id), "5")
    derecho = Derecho.objects.get(account=acc, codigo_producto="informe_natal")
    assert derecho.cantidad_restante == 5
    assert acc.movimientos.filter(tipo="otorgamiento", origen="ajuste", cantidad=5).count() == 1


@pytest.mark.django_db
def test_grant_credits_dos_llamadas_seguidas_suman_en_vez_de_pisarse():
    """`otorgar` es idempotente por external_id: sin uno único por invocación,
    la segunda recarga de la misma cantidad quedaría descartada como duplicado
    y esta cuenta se iría con 5 en vez de 10."""
    from api.models import Account, Derecho

    acc = Account.objects.create()
    call_command("grant_credits", str(acc.id), "5")
    call_command("grant_credits", str(acc.id), "5")
    derecho = Derecho.objects.get(account=acc, codigo_producto="informe_natal")
    assert derecho.cantidad_restante == 10


@pytest.mark.django_db
def test_grant_credits_unknown_account():
    with pytest.raises(CommandError):
        call_command("grant_credits", "999999", "1")
