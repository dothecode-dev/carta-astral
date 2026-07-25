"""El login Apple canjea el authorization_code y guarda el refresh_token.

Sin ese token guardado no hay forma de revocar en el borrado (Apple no ofrece
otro camino), pero un canje fallido NUNCA debe romper el login.
"""

import pytest
from rest_framework.test import APIClient

from api.sso import VerifiedIdentity


@pytest.fixture
def apple_login(monkeypatch, settings):
    """Login Apple con el id_token ya validado; devuelve el poster de la app."""
    settings.APPLE_AUD = "com.cartaastral.app"
    import api.views as views

    monkeypatch.setattr(
        views, "validate_apple",
        lambda id_token, nonce=None: VerifiedIdentity("apple", "SUB1", "u@x.com", True),
    )

    def _post(body):
        return APIClient().post("/api/auth/apple", body, format="json")

    return _post


@pytest.mark.django_db
def test_login_stores_refresh_token_from_authorization_code(apple_login, monkeypatch):
    from api import apple as apple_client
    from api.models import ProviderIdentity
    import api.views as views

    monkeypatch.setattr(views.apple, "is_configured", lambda: True)
    monkeypatch.setattr(views.apple, "exchange_code", lambda code: f"rt-for-{code}")

    resp = apple_login({"id_token": "tok", "authorization_code": "CODE9"})

    assert resp.status_code == 200
    ident = ProviderIdentity.objects.get(provider="apple", sub="SUB1")
    assert ident.refresh_token == "rt-for-CODE9"
    assert apple_client  # el módulo existe y es el que usa la vista


@pytest.mark.django_db
def test_login_without_authorization_code_still_works(apple_login, monkeypatch):
    from api.models import ProviderIdentity
    import api.views as views

    def _never(code):
        raise AssertionError("no debería canjear sin authorization_code")

    monkeypatch.setattr(views.apple, "is_configured", lambda: True)
    monkeypatch.setattr(views.apple, "exchange_code", _never)

    resp = apple_login({"id_token": "tok"})

    assert resp.status_code == 200
    assert ProviderIdentity.objects.get(provider="apple", sub="SUB1").refresh_token == ""


@pytest.mark.django_db
def test_failed_exchange_does_not_break_login(apple_login, monkeypatch):
    """Apple caído en el canje: el usuario entra igual, sin refresh_token."""
    from api.models import ProviderIdentity
    import api.views as views

    def _boom(code):
        from api.apple import AppleError
        raise AppleError("apple respondió 500")

    monkeypatch.setattr(views.apple, "is_configured", lambda: True)
    monkeypatch.setattr(views.apple, "exchange_code", _boom)

    resp = apple_login({"id_token": "tok", "authorization_code": "CODE9"})

    assert resp.status_code == 200
    assert "token" in resp.data
    assert ProviderIdentity.objects.get(provider="apple", sub="SUB1").refresh_token == ""


@pytest.mark.django_db
def test_no_exchange_when_apple_not_configured(apple_login, monkeypatch):
    """Sin las credenciales del server API no se intenta la llamada."""
    import api.views as views

    def _never(code):
        raise AssertionError("no debería canjear sin credenciales")

    monkeypatch.setattr(views.apple, "is_configured", lambda: False)
    monkeypatch.setattr(views.apple, "exchange_code", _never)

    assert apple_login({"id_token": "tok", "authorization_code": "CODE9"}).status_code == 200


@pytest.mark.django_db
def test_google_login_ignores_authorization_code(monkeypatch, settings):
    """El canje es sólo de Apple: Google no debe tocar ese camino."""
    settings.GOOGLE_AUD = "client.id"
    import api.views as views

    monkeypatch.setattr(
        views, "validate_google",
        lambda id_token, nonce=None: VerifiedIdentity("google", "G1", "g@x.com", True),
    )
    monkeypatch.setattr(views.apple, "is_configured", lambda: True)
    monkeypatch.setattr(
        views.apple, "exchange_code",
        lambda code: (_ for _ in ()).throw(AssertionError("google no canjea con apple")),
    )

    resp = APIClient().post(
        "/api/auth/google", {"id_token": "tok", "authorization_code": "X"}, format="json"
    )
    assert resp.status_code == 200


@pytest.mark.django_db
def test_relogin_refreshes_the_stored_token(apple_login, monkeypatch):
    """Segundo login del mismo sub: el token nuevo pisa al viejo (el viejo ya no sirve)."""
    from api.models import ProviderIdentity
    import api.views as views

    monkeypatch.setattr(views.apple, "is_configured", lambda: True)
    monkeypatch.setattr(views.apple, "exchange_code", lambda code: "rt-primero")
    apple_login({"id_token": "tok", "authorization_code": "C1"})

    monkeypatch.setattr(views.apple, "exchange_code", lambda code: "rt-segundo")
    apple_login({"id_token": "tok", "authorization_code": "C2"})

    idents = ProviderIdentity.objects.filter(provider="apple", sub="SUB1")
    assert idents.count() == 1
    assert idents.first().refresh_token == "rt-segundo"
