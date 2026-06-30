import pytest


class _FakeValidator:
    """Reemplaza la verificación RS256/JWKS; devuelve claims fijos."""
    def __init__(self, claims):
        self.claims = claims

    def __call__(self, id_token, nonce=None):
        if id_token == "bad":
            from api.sso import SSOError
            raise SSOError("firma inválida")
        return self.claims


def test_validate_apple_returns_verified_identity(monkeypatch, settings):
    settings.APPLE_AUD = "com.app.id"
    import api.sso as sso
    monkeypatch.setattr(sso, "_build_apple_validator", lambda: _FakeValidator(
        {"sub": "APPLE123", "email": "u@x.com", "email_verified": "true"}
    ))
    vid = sso.validate_apple("good")
    assert vid.provider == "apple"
    assert vid.sub == "APPLE123"
    assert vid.email == "u@x.com"
    assert vid.email_verified is True


def test_validate_apple_fail_closed_without_aud(settings):
    settings.APPLE_AUD = ""
    import api.sso as sso
    with pytest.raises(sso.SSONotConfigured):
        sso.validate_apple("whatever")


def test_validate_google_rejects_bad_signature(monkeypatch, settings):
    settings.GOOGLE_AUD = "client.id"
    import api.sso as sso
    monkeypatch.setattr(sso, "_build_google_validator", lambda: _FakeValidator({}))
    with pytest.raises(sso.SSOError):
        sso.validate_google("bad")


def test_validate_google_returns_verified_identity(monkeypatch, settings):
    settings.GOOGLE_AUD = "client.id"
    import api.sso as sso
    monkeypatch.setattr(sso, "_build_google_validator", lambda: _FakeValidator(
        {"sub": "GOOGLE123", "email": "g@x.com", "email_verified": True}
    ))
    vid = sso.validate_google("good")
    assert vid.provider == "google"
    assert vid.sub == "GOOGLE123"
    assert vid.email == "g@x.com"
    assert vid.email_verified is True


def test_validate_google_fail_closed_without_aud(settings):
    settings.GOOGLE_AUD = ""
    import api.sso as sso
    with pytest.raises(sso.SSONotConfigured):
        sso.validate_google("whatever")
