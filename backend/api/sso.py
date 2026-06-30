"""Validación local de id_token de Apple/Google contra JWKS.

Mismo patrón de testeabilidad que el cliente Anthropic: una función
_build_<provider>_validator() aislada construye el verificador real (red +
JWKS + RS256); la lógica recibe el validator inyectado, así los tests lo
reemplazan por un fake sin tocar red.
"""

import logging
from dataclasses import dataclass

import jwt
from django.conf import settings

logger = logging.getLogger(__name__)


class SSOError(Exception):
    """id_token inválido (firma/iss/aud/exp/nonce)."""


class SSONotConfigured(Exception):
    """Falta APPLE_AUD/GOOGLE_AUD => fail-closed."""


@dataclass
class VerifiedIdentity:
    provider: str
    sub: str
    email: str
    email_verified: bool


def _coerce_verified(value) -> bool:
    return value in (True, "true", "True", 1, "1")


class _JwksValidator:
    """Verifica firma RS256 contra el JWKS del proveedor, e iss/aud/exp/nonce."""

    def __init__(self, jwks_url: str, issuer: str, audience: str):
        self.jwks_url = jwks_url
        self.issuer = issuer
        self.audience = audience

    def _signing_key(self, id_token: str):
        client = jwt.PyJWKClient(self.jwks_url, cache_keys=True)
        try:
            return client.get_signing_key_from_jwt(id_token)
        except Exception as exc:  # rotación de claves / kid faltante
            logger.warning("jwks signing key lookup failed: %s", exc)
            raise SSOError("no se pudo obtener la clave de firma") from exc

    def __call__(self, id_token: str, nonce=None) -> dict:
        key = self._signing_key(id_token)
        try:
            claims = jwt.decode(
                id_token, key.key, algorithms=["RS256"],
                audience=self.audience, issuer=self.issuer,
            )
        except jwt.PyJWTError as exc:
            logger.warning("id_token rejected: %s", exc)
            raise SSOError(str(exc)) from exc
        if nonce is not None and claims.get("nonce") != nonce:
            raise SSOError("nonce mismatch")
        return claims


def _build_apple_validator():
    return _JwksValidator(settings.APPLE_JWKS_URL, settings.APPLE_ISS, settings.APPLE_AUD)


def _build_google_validator():
    return _JwksValidator(settings.GOOGLE_JWKS_URL, settings.GOOGLE_ISS, settings.GOOGLE_AUD)


def _validate(provider: str, aud: str, build_validator, id_token: str, nonce):
    if not aud:
        raise SSONotConfigured(f"{provider.upper()}_AUD no configurado")
    claims = build_validator()(id_token, nonce)
    return VerifiedIdentity(
        provider=provider,
        sub=claims["sub"],
        email=claims.get("email", ""),
        email_verified=_coerce_verified(claims.get("email_verified", False)),
    )


def validate_apple(id_token: str, nonce=None) -> VerifiedIdentity:
    return _validate("apple", settings.APPLE_AUD, _build_apple_validator, id_token, nonce)


def validate_google(id_token: str, nonce=None) -> VerifiedIdentity:
    return _validate("google", settings.GOOGLE_AUD, _build_google_validator, id_token, nonce)
