import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient
from api.auth import create_session
from api.canje import canjear, devolver, puede
from api.identity import sub_hash
from api.models import Account, Derecho, SubTombstone
from api.sso import VerifiedIdentity


def _gastar_lecturas_breves(cuenta, make_chart, n):
    """Consume `n` lecturas breves por el camino real (`canje.canjear`).

    Antes acá se hacía `acc.free_balance = 0`, que ya no consume nada: desde
    el modelo de canje el gasto vive en el `Derecho` y en sus `Movimiento`,
    y el campo viejo quedó de adorno (lo borra la 13c). Un test que siga
    tocando el campo prueba que el campo cambia, no que el usuario gastó.
    """
    for _ in range(n):
        canjear(cuenta, "leer_breve", make_chart(account=cuenta))


@pytest.mark.django_db
def test_delete_account_endpoint_revokes_and_tombstones(make_chart):
    from api.accounts import resolve_account

    acc = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    _gastar_lecturas_breves(acc, make_chart, settings.INSTALL_FREE_CREDITS)
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    assert c.delete("/api/account/").status_code == 204
    # token revocado
    assert c.get("/api/account/").status_code in (401, 403)
    # tombstone con free consumido
    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "S"))
    assert tomb.free_credits_consumed == settings.INSTALL_FREE_CREDITS
    # cuenta borrada
    assert not Account.objects.filter(pk=acc.pk).exists()


@pytest.mark.django_db
def test_recreate_after_delete_has_no_free(make_chart):
    from api.accounts import resolve_account

    acc = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    _gastar_lecturas_breves(acc, make_chart, settings.INSTALL_FREE_CREDITS)
    from api.deletion import delete_account
    delete_account(acc)
    again = resolve_account(VerifiedIdentity("apple", "S", "u@x.com", True))
    assert not Derecho.objects.filter(account=again, codigo_producto="lectura_breve").exists()
    assert puede(again, "leer_breve") is False


@pytest.mark.django_db
@override_settings(INSTALL_FREE_CREDITS=3)
def test_el_tombstone_cuenta_lo_gastado_segun_los_movimientos(make_chart):
    """El número anti-abuso sale del libro de movimientos, no del campo viejo.

    `canjear` no toca `free_balance`: con el cálculo viejo esta cuenta —que
    gastó 2 de 3 lecturas— dejaba el tombstone en 0 y borrar la cuenta para
    volver a entrar regalaba las 3 de nuevo.
    """
    from api.accounts import resolve_account
    from api.deletion import delete_account

    acc = resolve_account(VerifiedIdentity("apple", "MOV", "m@x.com", True))
    _gastar_lecturas_breves(acc, make_chart, 2)
    assert acc.free_balance == 3  # el campo viejo quedó intacto: no es la fuente

    delete_account(acc)

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "MOV"))
    assert tomb.free_credits_consumed == 2


@pytest.mark.django_db
@override_settings(INSTALL_FREE_CREDITS=3)
def test_borrar_una_cuenta_sin_derechos_no_baja_el_tombstone():
    """La puerta de atrás más peligrosa del cálculo.

    Con el tombstone agotado, el alta NO otorga nada: la cuenta nueva no
    tiene ni `Derecho` ni un solo `Movimiento` de `lectura_breve`. Si el
    consumido se contara sumando movimientos de consumo, daría 0, el
    `update_or_create` bajaría el tombstone de 3 a 0 y el ciclo
    borrar → volver a entrar regalaría 3 lecturas cada vez, para siempre.
    """
    from api.accounts import resolve_account
    from api.deletion import delete_account
    from api.models import Movimiento

    SubTombstone.objects.create(sub_hash=sub_hash("apple", "AGOT"), free_credits_consumed=3)
    acc = resolve_account(VerifiedIdentity("apple", "AGOT", "a@x.com", True))
    assert not Derecho.objects.filter(account=acc).exists()
    assert not Movimiento.objects.filter(account=acc).exists()

    delete_account(acc)

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "AGOT"))
    assert tomb.free_credits_consumed == 3


@pytest.mark.django_db
@override_settings(INSTALL_FREE_CREDITS=3)
def test_el_tombstone_no_cuenta_una_lectura_devuelta(make_chart):
    """Contrapunto del anterior, del otro lado: si la generación falló y el
    derecho se repuso, el usuario no gastó nada y el tombstone no puede
    cobrárselo."""
    from api.accounts import resolve_account
    from api.deletion import delete_account

    acc = resolve_account(VerifiedIdentity("apple", "DEV", "d@x.com", True))
    carta = make_chart(account=acc)
    canjear(acc, "leer_breve", carta)
    devolver(acc, "lectura_breve", external_id="falló-la-generación", chart=carta)

    delete_account(acc)

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "DEV"))
    assert tomb.free_credits_consumed == 0


@pytest.mark.django_db
@override_settings(INSTALL_FREE_CREDITS=3)
def test_el_tombstone_de_una_segunda_vida_suma_lo_de_la_primera(make_chart):
    """Segunda vida con tombstone parcial: el alta regala sólo 1 lectura (3-2)
    y el usuario la gasta. El tombstone tiene que quedar en 3, no en 1: el
    `update_or_create` PISA el valor anterior, así que un cálculo que sólo
    mire esta vida borraría lo que se consumió en la anterior."""
    from api.accounts import resolve_account
    from api.deletion import delete_account

    SubTombstone.objects.create(sub_hash=sub_hash("apple", "SEG"), free_credits_consumed=2)
    acc = resolve_account(VerifiedIdentity("apple", "SEG", "s@x.com", True))
    assert Derecho.objects.get(account=acc, codigo_producto="lectura_breve").cantidad_restante == 1
    _gastar_lecturas_breves(acc, make_chart, 1)

    delete_account(acc)

    tomb = SubTombstone.objects.get(sub_hash=sub_hash("apple", "SEG"))
    assert tomb.free_credits_consumed == 3


@pytest.mark.django_db
def test_unauthenticated_delete_rejected():
    assert APIClient().delete("/api/account/").status_code in (401, 403)
