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
def test_grant_credits_cada_invocacion_deja_su_propio_movimiento_trazable():
    """El `external_id` (`uuid4()`) no es idempotencia: este comando nunca la
    tuvo, ni con `ledger.grant_paid` ni ahora con `canje.otorgar` — es aditivo
    a propósito, correrlo dos veces es acreditar dos veces (`Movimiento.
    external_id` es único sólo cuando no está vacío: la `UniqueConstraint` es
    parcial, `condition=Q(external_id__gt="")`, así que dos `otorgar` con
    external_id="" también suman, no se pisan).

    Lo que el `uuid4()` sí da es trazabilidad: cada recarga manual queda como
    su propio `Movimiento`, identificable en el admin y en la auditoría. Eso
    es lo que este test verifica."""
    from api.models import Account, Derecho

    acc = Account.objects.create()
    call_command("grant_credits", str(acc.id), "5")
    call_command("grant_credits", str(acc.id), "5")

    derecho = Derecho.objects.get(account=acc, codigo_producto="informe_natal")
    assert derecho.cantidad_restante == 10  # aditivo, no idempotente

    movimientos = list(
        acc.movimientos.filter(tipo="otorgamiento", origen="ajuste", cantidad=5)
    )
    assert len(movimientos) == 2
    ids = [m.external_id for m in movimientos]
    assert all(ids)  # ninguno vacío
    assert ids[0] != ids[1]  # cada invocación, su propio external_id


@pytest.mark.django_db
def test_grant_credits_unknown_account():
    with pytest.raises(CommandError):
        call_command("grant_credits", "999999", "1")
