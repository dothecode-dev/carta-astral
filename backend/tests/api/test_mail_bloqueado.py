"""`MailBloqueado` (RF16): quien disputó no entra ni compra con cuenta."""

import pytest

from api.models import MailBloqueado

pytestmark = pytest.mark.django_db


def test_se_normaliza_y_es_idempotente():
    MailBloqueado.bloquear("  Ana@Mail.com ", motivo="disputa", dispute_id="du_1")
    MailBloqueado.bloquear("ana@mail.com", motivo="disputa", dispute_id="du_1")

    assert MailBloqueado.objects.count() == 1
    assert MailBloqueado.bloqueado("ANA@mail.com") is True
    assert MailBloqueado.bloqueado("otra@mail.com") is False
    assert MailBloqueado.bloqueado("") is False


def test_pedir_codigo_responde_202_sin_mandar_nada(client, monkeypatch):
    """Sin distinguir del caso normal (no se revela quién está bloqueado)."""
    from api import notificaciones
    from api.models import CodigoAcceso

    MailBloqueado.bloquear("ana@mail.com", motivo="disputa")
    monkeypatch.setattr(notificaciones, "enviar_codigo", lambda *a, **k: pytest.fail("no debía mandar"))

    r = client.post("/api/auth/email/codigo", {"email": "ana@mail.com"})

    assert r.status_code == 202
    assert not CodigoAcceso.objects.exists()


def test_google_con_un_mail_bloqueado_es_403(client, monkeypatch):
    from api import views
    from api.models import Account
    from api.sso import VerifiedIdentity

    MailBloqueado.bloquear("ana@mail.com", motivo="disputa")
    monkeypatch.setattr(
        views.GoogleAuthView, "validator",
        lambda self, token, nonce=None: VerifiedIdentity(
            provider="google", sub="s1", email="ana@mail.com", email_verified=True,
        ),
    )

    r = client.post("/api/auth/google", {"id_token": "x"})

    assert r.status_code == 403
    assert r.json()["motivo"] == "bloqueado"
    assert not Account.objects.exists()


def test_el_checkout_con_cuenta_bloqueada_es_403(account_client, settings):
    settings.STRIPE_SECRET_KEY = "sk_test_x"
    settings.STRIPE_PRODUCTOS = {"informe_natal": "prod_natal"}
    # `account_client` arranca sin mail: se le pone uno para poder bloquearlo.
    account_client.account.email = "ana@mail.com"
    account_client.account.save(update_fields=["email"])
    MailBloqueado.bloquear(account_client.account.email, motivo="disputa")

    r = account_client.post("/api/checkout/", {"producto": "informe_natal"})

    assert r.status_code == 403
    assert r.json()["motivo"] == "bloqueado"
