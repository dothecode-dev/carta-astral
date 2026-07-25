"""Cliente del Apple ID server API: client_secret, canje de code y revoke.

La red se reemplaza por un poster fake (mismo patrón que el validador de sso.py).
La clave privada de test es una EC P-256 generada al vuelo: Apple firma el
client_secret con ES256 y una clave RSA no sirve para verificar el contrato.
"""

import json

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


@pytest.fixture
def ec_key_pair():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


@pytest.fixture
def apple_settings(settings, ec_key_pair):
    pem, public_key = ec_key_pair
    settings.APPLE_AUD = "com.cartaastral.app"
    settings.APPLE_TEAM_ID = "TEAM123456"
    settings.APPLE_KEY_ID = "KEY7890"
    settings.APPLE_PRIVATE_KEY = pem
    return public_key


class _FakePoster:
    """Captura la llamada y devuelve una respuesta canned."""

    def __init__(self, response=None, error=None):
        self.response = response if response is not None else {}
        self.error = error
        self.calls = []

    def __call__(self, url, data):
        self.calls.append((url, data))
        if self.error is not None:
            raise self.error
        return self.response


def test_build_client_secret_is_es256_signed_with_apple_claims(apple_settings):
    from api import apple

    public_key = apple_settings
    token = apple.build_client_secret()

    header = jwt.get_unverified_header(token)
    assert header["alg"] == "ES256"
    assert header["kid"] == "KEY7890"

    claims = jwt.decode(
        token, public_key, algorithms=["ES256"], audience="https://appleid.apple.com"
    )
    assert claims["iss"] == "TEAM123456"
    assert claims["sub"] == "com.cartaastral.app"  # el bundle id, no el team
    assert claims["exp"] > claims["iat"]


def test_build_client_secret_without_config_raises_not_configured(settings):
    from api import apple

    settings.APPLE_TEAM_ID = ""
    settings.APPLE_KEY_ID = ""
    settings.APPLE_PRIVATE_KEY = ""
    with pytest.raises(apple.AppleNotConfigured):
        apple.build_client_secret()


def test_is_configured_needs_the_four_values(settings, ec_key_pair):
    from api import apple

    pem, _ = ec_key_pair
    settings.APPLE_AUD = "com.cartaastral.app"
    settings.APPLE_TEAM_ID = "TEAM123456"
    settings.APPLE_KEY_ID = "KEY7890"
    settings.APPLE_PRIVATE_KEY = pem
    assert apple.is_configured() is True

    settings.APPLE_KEY_ID = ""
    assert apple.is_configured() is False


def test_exchange_code_posts_grant_and_returns_refresh_token(apple_settings, monkeypatch):
    from api import apple

    poster = _FakePoster({"refresh_token": "rt-123", "access_token": "at-456"})
    monkeypatch.setattr(apple, "_post_form", poster)

    assert apple.exchange_code("the-code") == "rt-123"

    url, data = poster.calls[0]
    assert url == apple.APPLE_TOKEN_URL
    assert data["grant_type"] == "authorization_code"
    assert data["code"] == "the-code"
    assert data["client_id"] == "com.cartaastral.app"
    assert data["client_secret"]  # el JWT firmado


def test_exchange_code_without_refresh_token_raises(apple_settings, monkeypatch):
    from api import apple

    monkeypatch.setattr(apple, "_post_form", _FakePoster({"error": "invalid_grant"}))
    with pytest.raises(apple.AppleError):
        apple.exchange_code("stale-code")


def test_revoke_posts_token_and_hint(apple_settings, monkeypatch):
    from api import apple

    poster = _FakePoster({})
    monkeypatch.setattr(apple, "_post_form", poster)

    apple.revoke("rt-123")

    url, data = poster.calls[0]
    assert url == apple.APPLE_REVOKE_URL
    assert data["token"] == "rt-123"
    assert data["token_type_hint"] == "refresh_token"
    assert data["client_id"] == "com.cartaastral.app"


def test_revoke_propagates_apple_error(apple_settings, monkeypatch):
    from api import apple

    monkeypatch.setattr(
        apple, "_post_form", _FakePoster(error=apple.AppleError("500 del server"))
    )
    with pytest.raises(apple.AppleError):
        apple.revoke("rt-123")


def test_post_form_maps_http_error_to_apple_error(monkeypatch):
    """El error de red/HTTP no se escapa crudo: siempre sale tipado."""
    import urllib.error

    from api import apple

    def boom(*args, **kwargs):
        raise urllib.error.HTTPError(
            apple.APPLE_TOKEN_URL, 400, "Bad Request", {}, None
        )

    monkeypatch.setattr(apple.urllib.request, "urlopen", boom)
    with pytest.raises(apple.AppleError):
        apple._post_form(apple.APPLE_TOKEN_URL, {"a": "b"})


def test_post_form_parses_json_and_tolerates_empty_body(monkeypatch):
    """El revoke exitoso de Apple responde 200 con body vacío."""
    from api import apple

    class _Resp:
        def __init__(self, body):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        apple.urllib.request, "urlopen", lambda *a, **k: _Resp(json.dumps({"x": 1}).encode())
    )
    assert apple._post_form(apple.APPLE_TOKEN_URL, {"a": "b"}) == {"x": 1}

    monkeypatch.setattr(apple.urllib.request, "urlopen", lambda *a, **k: _Resp(b""))
    assert apple._post_form(apple.APPLE_REVOKE_URL, {"a": "b"}) == {}
