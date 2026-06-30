import pytest
from rest_framework.test import APIClient
from api.sso import VerifiedIdentity


@pytest.mark.django_db
def test_apple_auth_creates_session(monkeypatch, settings):
    settings.APPLE_AUD = "com.app"
    import api.views as views
    monkeypatch.setattr(
        views, "validate_apple",
        lambda id_token, nonce=None: VerifiedIdentity("apple", "S1", "u@x.com", True),
    )
    resp = APIClient().post("/api/auth/apple", {"id_token": "tok"}, format="json")
    assert resp.status_code == 200
    assert "token" in resp.data
    assert resp.data["credits_available"] == 1
    from api.identity import hash_token
    from api.models import Session
    assert Session.objects.filter(token_hash=hash_token(resp.data["token"])).exists()


@pytest.mark.django_db
def test_auth_503_when_not_configured(settings):
    settings.APPLE_AUD = ""
    resp = APIClient().post("/api/auth/apple", {"id_token": "tok"}, format="json")
    assert resp.status_code == 503


@pytest.mark.django_db
def test_auth_401_on_invalid_token(monkeypatch, settings):
    settings.GOOGLE_AUD = "client"
    import api.views as views
    from api.sso import SSOError

    def _boom(id_token, nonce=None):
        raise SSOError("firma inválida")
    monkeypatch.setattr(views, "validate_google", _boom)
    resp = APIClient().post("/api/auth/google", {"id_token": "bad"}, format="json")
    assert resp.status_code == 401
