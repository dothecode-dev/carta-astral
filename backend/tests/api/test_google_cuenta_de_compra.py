"""Entrar con Google a la cuenta que creó una compra sin cuenta.
Superficie de AUTENTICACIÓN (revisión final de «pagar es entrar», punto 4).

Quien paga sin cuenta con su Gmail queda con una cuenta SIN verificar (nadie
probó el mail todavía). Antes, entrar con Google caía en una cuenta nueva y
vacía, porque `resolver_cuenta` sólo enlaza por mail a cuentas verificadas.

Arreglo acotado: con un mail que Google VERIFICÓ se acepta además UNA cuenta
sin verificar que nació de una compra (identidad email propia + checkout
anónimo con `cuenta_nueva`). Probar el mail con Google vale lo mismo que
probarlo con el código (RF17): la cuenta se verifica y se cierran las demás
sesiones —las del navegador que pagó, que pudo ser de otra persona—.
"""

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from api import compra_anonima
from api.accounts import resolver_cuenta
from api.auth import create_session
from api.identity import hash_token
from api.models import Account, PasarelaCheckout, ProviderIdentity, Session
from api.sso import VerifiedIdentity
from tests.api.conftest import SESSION_ANONIMA, con_mail

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("django_cache_cleared")]

MAIL = "nueva@example.com"
NONCE = "n0nce-google"


@pytest.fixture
def google(monkeypatch, settings):
    """`google(email, verificado)` entra por `/api/auth/google` con esa identidad."""
    import api.views as views

    settings.GOOGLE_AUD = "client"

    def _entrar(email=MAIL, verificado=True, sub="G-1"):
        monkeypatch.setattr(
            views, "validate_google",
            lambda id_token, nonce=None: VerifiedIdentity("google", sub, email, verificado),
        )
        return APIClient().post("/api/auth/google", {"id_token": "tok"}, format="json")

    return _entrar


@pytest.fixture
def pagada(entregar_anonima, anonima, sin_hilo):
    """Compra sin cuenta pagada con un mail sin cuenta, y el navegador que
    pagó ya adentro por el nonce. Devuelve `(cuenta, token_del_pagador)`."""
    assert entregar_anonima(con_mail(MAIL)).status_code == 200
    anonima.refresh_from_db()
    assert anonima.cuenta_nueva is True
    anonima.nonce_hash = hash_token(NONCE)
    anonima.save(update_fields=["nonce_hash"])
    canje = compra_anonima.canjear(SESSION_ANONIMA, NONCE)
    assert canje["estado"] == "sesion"
    return anonima.account, canje["token"]


def _sesion_viva(token):
    return Session.objects.filter(token_hash=hash_token(token)).exists()


# (a) ------------------------------------------------------------------------


def test_google_verificado_entra_a_la_cuenta_de_la_compra(google, pagada):
    cuenta, token_pagador = pagada

    r = google(email="Nueva@Example.com")

    assert r.status_code == 200
    assert r.data["account_id"] == cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is True
    assert ProviderIdentity.objects.get(provider="google", sub="G-1").account_id == cuenta.pk
    # La sesión del navegador que pagó muere; la de Google es la única.
    assert not _sesion_viva(token_pagador)
    assert _sesion_viva(r.data["token"])
    assert Session.objects.filter(account=cuenta).count() == 1
    assert Account.objects.filter(email__iexact=MAIL).count() == 1


def test_despues_el_nonce_ya_no_abre_sesion(google, pagada):
    """Con la cuenta verificada, el canje cae a la rama del código (nunca
    sesión): el pagador no puede volver a entrar a la cuenta de la dueña."""
    google()
    PasarelaCheckout.objects.filter(checkout_id=SESSION_ANONIMA).update(canjeado_at=None)

    assert compra_anonima.canjear(SESSION_ANONIMA, NONCE)["estado"] != "sesion"


def test_resolver_cuenta_no_la_cuenta_como_creada(pagada):
    cuenta, _ = pagada
    assert resolver_cuenta(VerifiedIdentity("google", "G-2", MAIL, True)) == (cuenta, False)


# (b) ------------------------------------------------------------------------


def test_google_con_mail_sin_verificar_no_enlaza(google, pagada):
    """Pre-account-hijacking: un mail que Google no verificó no prueba nada."""
    cuenta, token_pagador = pagada

    r = google(verificado=False)

    assert r.status_code == 200
    assert r.data["account_id"] != cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is False
    assert _sesion_viva(token_pagador)
    assert not ProviderIdentity.objects.filter(provider="google", account=cuenta).exists()


# (c) ------------------------------------------------------------------------


def _sin_verificar_con_identidad(email=MAIL):
    cuenta = Account.objects.create(email=email, email_verified=False)
    ProviderIdentity.objects.create(provider="email", sub=email, account=cuenta)
    return cuenta


@pytest.mark.parametrize("checkout", [
    None,  # ninguna compra detrás
    {"anonimo": True, "cuenta_nueva": False},  # la compra no la creó
    {"anonimo": False, "cuenta_nueva": True},  # checkout con cuenta, no anónimo
])
def test_cuenta_sin_verificar_que_no_nacio_de_una_compra_no_enlaza(google, checkout):
    cuenta = _sin_verificar_con_identidad()
    if checkout is not None:
        PasarelaCheckout.objects.create(
            checkout_id="cs_otra", account=cuenta, codigo_producto="informe_natal",
            acreditado_at=timezone.now(), **checkout,
        )
    viva = create_session(cuenta)

    r = google()

    assert r.status_code == 200
    assert r.data["account_id"] != cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is False
    assert _sesion_viva(viva)


def test_sin_identidad_email_propia_no_enlaza(google):
    """La compra la creó, pero la identidad email es de OTRA cuenta (o no
    existe): no es la cuenta a la que entra el mail."""
    cuenta = Account.objects.create(email=MAIL, email_verified=False)
    PasarelaCheckout.objects.create(
        checkout_id="cs_otra", account=cuenta, codigo_producto="informe_natal",
        anonimo=True, cuenta_nueva=True, acreditado_at=timezone.now(),
    )

    r = google()

    assert r.data["account_id"] != cuenta.pk


# Prioridad --------------------------------------------------------------------


def test_una_cuenta_verificada_con_el_mismo_mail_gana(google, pagada):
    cuenta_compra, token_pagador = pagada
    verificada = Account.objects.create(email=MAIL, email_verified=True)

    r = google()

    assert r.data["account_id"] == verificada.pk
    cuenta_compra.refresh_from_db()
    assert cuenta_compra.email_verified is False
    assert _sesion_viva(token_pagador)


# Lo que ya andaba -------------------------------------------------------------


def test_google_con_mail_nuevo_sigue_creando_cuenta(google):
    r = google(email="otra@example.com")
    assert Account.objects.get(pk=r.data["account_id"]).email == "otra@example.com"


def test_el_login_por_codigo_sigue_verificando_y_cerrando_sesiones(client, pagada, monkeypatch):
    """RF17, ahora por la lógica compartida."""
    from api import codigos_acceso, notificaciones

    cuenta, token_pagador = pagada
    monkeypatch.setattr(notificaciones, "enviar_codigo", lambda *a: None)
    _, claro, _ = codigos_acceso.pedir(MAIL)

    r = client.post(
        "/api/auth/email", {"email": MAIL, "codigo": claro},
        content_type="application/json",
    )

    assert r.status_code == 200, r.content
    assert r.json()["account_id"] == cuenta.pk
    cuenta.refresh_from_db()
    assert cuenta.email_verified is True
    assert not _sesion_viva(token_pagador)
