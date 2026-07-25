"""El borrado de cuenta revoca el token de Sign in with Apple (guideline 5.1.1(v)).

Decisión D2 de la mini-spec: si Apple falla, el borrado procede igual. El derecho
del usuario a que sus datos desaparezcan pesa más que la revocación.
"""

import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.models import Account, ProviderIdentity
from api.sso import VerifiedIdentity


class _SpyRevoke:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def __call__(self, token, token_type_hint="refresh_token"):
        self.calls.append(token)
        if self.error is not None:
            raise self.error


@pytest.fixture
def apple_account(db):
    """Cuenta creada por login Apple, con refresh_token ya guardado."""
    from api.accounts import resolve_account

    account = resolve_account(VerifiedIdentity("apple", "SUB1", "u@x.com", True))
    ProviderIdentity.objects.filter(provider="apple", sub="SUB1").update(refresh_token="rt-1")
    return account


@pytest.mark.django_db
def test_delete_account_revokes_the_apple_token(apple_account, monkeypatch):
    import api.deletion as deletion

    spy = _SpyRevoke()
    monkeypatch.setattr(deletion.apple, "is_configured", lambda: True)
    monkeypatch.setattr(deletion.apple, "revoke", spy)

    deletion.delete_account(apple_account)

    assert spy.calls == ["rt-1"]
    assert not Account.objects.filter(pk=apple_account.pk).exists()


@pytest.mark.django_db
def test_delete_proceeds_when_apple_revoke_fails(apple_account, monkeypatch, caplog):
    """Apple caído: la cuenta se borra igual y queda el rastro en el log."""
    import api.deletion as deletion
    from api.apple import AppleError

    monkeypatch.setattr(deletion.apple, "is_configured", lambda: True)
    monkeypatch.setattr(deletion.apple, "revoke", _SpyRevoke(error=AppleError("apple 500")))

    with caplog.at_level("ERROR"):
        deletion.delete_account(apple_account)

    assert not Account.objects.filter(pk=apple_account.pk).exists()
    assert not ProviderIdentity.objects.filter(sub="SUB1").exists()
    assert any("revoke" in r.message.lower() for r in caplog.records)


@pytest.mark.django_db
def test_no_network_call_when_apple_not_configured(apple_account, monkeypatch, caplog):
    import api.deletion as deletion

    def _never(token, token_type_hint="refresh_token"):
        raise AssertionError("no debería llamar a Apple sin credenciales")

    monkeypatch.setattr(deletion.apple, "is_configured", lambda: False)
    monkeypatch.setattr(deletion.apple, "revoke", _never)

    with caplog.at_level("ERROR"):
        deletion.delete_account(apple_account)

    assert not Account.objects.filter(pk=apple_account.pk).exists()
    # config incompleta con un token pendiente = anomalía que hay que ver en los logs
    assert any("revoke" in r.message.lower() for r in caplog.records)


@pytest.mark.django_db
def test_google_only_account_does_not_touch_apple(db, monkeypatch):
    import api.deletion as deletion
    from api.accounts import resolve_account

    def _never(token, token_type_hint="refresh_token"):
        raise AssertionError("cuenta sin identidad Apple no revoca")

    account = resolve_account(VerifiedIdentity("google", "G1", "g@x.com", True))
    monkeypatch.setattr(deletion.apple, "is_configured", lambda: True)
    monkeypatch.setattr(deletion.apple, "revoke", _never)

    deletion.delete_account(account)

    assert not Account.objects.filter(pk=account.pk).exists()


@pytest.mark.django_db
def test_apple_identity_without_token_is_skipped(db, monkeypatch):
    """Login viejo (previo a esta feature): no hay token, no hay llamada."""
    import api.deletion as deletion
    from api.accounts import resolve_account

    def _never(token, token_type_hint="refresh_token"):
        raise AssertionError("sin refresh_token no hay nada que revocar")

    account = resolve_account(VerifiedIdentity("apple", "OLD", "old@x.com", True))
    monkeypatch.setattr(deletion.apple, "is_configured", lambda: True)
    monkeypatch.setattr(deletion.apple, "revoke", _never)

    deletion.delete_account(account)

    assert not Account.objects.filter(pk=account.pk).exists()


@pytest.mark.django_db
def test_delete_endpoint_revokes_too(apple_account, monkeypatch):
    """El camino real del usuario (DELETE /api/account/), no sólo la función."""
    import api.deletion as deletion

    spy = _SpyRevoke()
    monkeypatch.setattr(deletion.apple, "is_configured", lambda: True)
    monkeypatch.setattr(deletion.apple, "revoke", spy)

    token = create_session(apple_account)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    assert client.delete("/api/account/").status_code == 204
    assert spy.calls == ["rt-1"]
