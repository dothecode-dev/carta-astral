"""Lo que la pantalla de cuenta necesita saber: quién sos y qué compraste.

`/api/account/` no devolvía el email, así que la cuenta no podía mostrar con
cuál entraste —y con Google y Apple es fácil terminar en la cuenta equivocada
sin darse cuenta—.

`/api/compras/` es nuevo: el historial de lo pagado. Mismo aislamiento que las
cartas: las tuyas, y las de otro no existen.
"""

import pytest
from django.utils import timezone

from api.models import PasarelaCheckout

pytestmark = pytest.mark.django_db


def test_la_cuenta_dice_con_que_mail_entraste(account_client):
    account_client.account.email = "gustavo@example.com"
    account_client.account.save(update_fields=["email"])

    assert account_client.get("/api/account/").json()["email"] == "gustavo@example.com"


def test_una_cuenta_sin_mail_devuelve_vacio_no_rompe(account_client):
    """Se puede entrar con Apple ocultando el mail: la pantalla muestra lo que
    haya, pero el campo tiene que estar siempre."""
    assert account_client.get("/api/account/").json()["email"] == ""


def test_sin_sesion_no_hay_compras(client):
    assert client.get("/api/compras/").status_code == 401


def test_lista_las_compras_acreditadas(account_client):
    PasarelaCheckout.objects.create(
        checkout_id="cs_1", account=account_client.account,
        codigo_producto="pack_5_natal", acreditado_at=timezone.now(),
    )

    compras = account_client.get("/api/compras/").json()["compras"]

    assert len(compras) == 1
    assert compras[0]["codigo_producto"] == "pack_5_natal"
    assert compras[0]["acreditada"] is True
    assert "created_at" in compras[0]


def test_una_compra_que_no_acredito_se_ve_como_pendiente(account_client):
    """Si pagó y el webhook todavía no llegó, la compra existe y hay que
    mostrarla: esconderla haría pensar que se perdió la plata."""
    PasarelaCheckout.objects.create(
        checkout_id="cs_2", account=account_client.account, codigo_producto="informe_natal",
    )

    assert account_client.get("/api/compras/").json()["compras"][0]["acreditada"] is False


def test_las_compras_de_otra_cuenta_no_se_ven(account_client, make_account):
    """Mismo criterio que una carta ajena."""
    PasarelaCheckout.objects.create(
        checkout_id="cs_ajena", account=make_account(), codigo_producto="informe_natal",
        acreditado_at=timezone.now(),
    )

    assert account_client.get("/api/compras/").json()["compras"] == []


def test_no_expone_el_payment_intent_ni_el_id_de_stripe(account_client):
    """La pantalla necesita qué compraste y cuándo. Los identificadores de la
    pasarela son para el soporte, no para el navegador."""
    PasarelaCheckout.objects.create(
        checkout_id="cs_3", account=account_client.account,
        codigo_producto="informe_natal", payment_intent="pi_secreto",
        acreditado_at=timezone.now(),
    )

    compra = account_client.get("/api/compras/").json()["compras"][0]

    assert set(compra) == {"codigo_producto", "acreditada", "created_at"}


def test_vienen_de_la_mas_nueva_a_la_mas_vieja(account_client):
    for i in range(3):
        PasarelaCheckout.objects.create(
            checkout_id=f"cs_{i}", account=account_client.account,
            codigo_producto="informe_natal", acreditado_at=timezone.now(),
        )

    fechas = [c["created_at"] for c in account_client.get("/api/compras/").json()["compras"]]

    assert fechas == sorted(fechas, reverse=True)
