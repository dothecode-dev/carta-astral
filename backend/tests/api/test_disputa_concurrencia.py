"""Concurrencia real sobre las disputas: la reposición de una compra y el
retiro de OTRA compra del mismo mail, a la vez. Superficie de ENTRADA (RF16).

El caso es el de dos compras del mismo mail que no comparten cuenta (una sin
cuenta disputada antes de su pago, EC16). Sin el lock de `MailBloqueado`, la
reposición no veía la disputa todavía sin
commitear de la otra compra, borraba el bloqueo y el retiro, que encontraba la
fila y no creaba otra, dejaba el mail libre con una disputa abierta.

Sólo corre contra Postgres: en SQLite `SELECT ... FOR UPDATE` se ignora. El
orden malo se FUERZA con eventos (dejarlo al planificador no lo reproducía:
medido el 18-10-2026, sin el lock pasaba diez de diez): el retiro de B se
detiene después de bloquear el mail y antes de crear su disputa, y recién ahí corre
la reposición de A entera. Con el lock, la reposición espera al retiro.
"""

import threading

import pytest
from django.utils import timezone

from api import disputas
from api.canje import aplicar_compra
from api.models import Disputa, MailBloqueado, PasarelaCheckout
from tests.api.concurrencia import en_hilos, requiere_postgres

ESPERA = 3  # segundos que el retiro de B le da a la reposición de A para colarse


def _compra(cuenta, checkout_id, pi):
    PasarelaCheckout.objects.create(
        checkout_id=checkout_id, account=cuenta, codigo_producto="informe_natal", moneda="usd",
        precio_centavos=500, payment_intent=pi, acreditado_at=timezone.now(),
    )
    aplicar_compra(cuenta, "informe_natal", 500, external_id=f"stripe:session:{checkout_id}", precio_centavos=500)


def _evento(dispute_id, pi):
    return {"id": dispute_id, "payment_intent": pi, "amount": 500, "currency": "usd", "reason": "fraudulent"}


@requiere_postgres
@pytest.mark.django_db(transaction=True)
def test_reponer_una_y_retirar_otra_del_mismo_mail_a_la_vez_deja_el_mail_bloqueado(make_account, monkeypatch):
    monkeypatch.setattr(disputas, "avisar_admin", lambda _texto: None)
    email = "ana@mail.com"
    cuenta = make_account(email=email)
    _compra(cuenta, "cs_a", "pi_a")
    # B: compra sin cuenta disputada antes de su pago (EC16). Con las dos en la
    # misma cuenta la carrera no existe: el ledger lockea la cuenta en los dos
    # caminos y eso ya los serializa.
    PasarelaCheckout.objects.create(
        checkout_id="cs_b", account=None, codigo_producto="informe_natal", moneda="usd",
        precio_centavos=500, anonimo=True, nonce_hash="x" * 64,
    )
    monkeypatch.setattr(
        disputas, "sesion_por_payment_intent",
        lambda pi: {"id": "cs_b", "customer_details": {"email": email}} if pi == "pi_b" else None,
    )
    disputas.procesar(_evento("du_a", "pi_a"), disputas.RETIRO)

    b_bloqueo = threading.Event()
    a_termino = threading.Event()
    asegurar_real = disputas._bloquear_y_lockear

    def asegurar_y_esperar(mail, dispute_id):
        asegurar_real(mail, dispute_id)
        if dispute_id == "du_b":
            # El mail ya está bloqueado (y, con el lock, la fila tomada): acá
            # se cuela la reposición de A antes de que B cree su disputa.
            b_bloqueo.set()
            a_termino.wait(ESPERA)

    monkeypatch.setattr(disputas, "_bloquear_y_lockear", asegurar_y_esperar)

    def operar(i):
        if i == 0:
            assert b_bloqueo.wait(ESPERA)
            disputas.procesar(_evento("du_a", "pi_a"), disputas.REPOSICION)
            a_termino.set()
        else:
            disputas.procesar(_evento("du_b", "pi_b"), disputas.RETIRO)

    _resultados, errores = en_hilos(operar, 2)

    assert not errores, errores
    assert Disputa.objects.get(dispute_id="du_b").estado == Disputa.ABIERTA
    assert MailBloqueado.bloqueado(email), "mail libre con una disputa abierta"
