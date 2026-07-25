"""Cliente del Apple ID server API: canje de authorization_code y revoke.

Apple exige (App Store guideline 5.1.1(v)) que el borrado de cuenta revoque el
token de Sign in with Apple. El `/auth/revoke` necesita un refresh_token, y ese
token sólo se consigue canjeando el authorization_code que llega EN EL LOGIN:
por eso el flujo se parte en dos momentos (ver docs/2026-07-25-spec-apple-sso-revoke.md).

Testeabilidad: la única función que toca la red es `_post_form`; los tests la
reemplazan por un fake, mismo patrón que el validador JWKS de sso.py. No se usa
`requests`/`httpx` a propósito: el backend no los tiene y son dos POST.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

import jwt
from django.conf import settings

logger = logging.getLogger(__name__)

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
APPLE_AUDIENCE = "https://appleid.apple.com"

# Apple rechaza client_secrets con exp a más de 6 meses. 1 hora alcanza y sobra:
# se firma uno nuevo en cada llamada.
CLIENT_SECRET_TTL = 3600
HTTP_TIMEOUT = 10


class AppleError(Exception):
    """Apple respondió un error, o la red falló."""


class AppleNotConfigured(Exception):
    """Faltan APPLE_TEAM_ID/APPLE_KEY_ID/APPLE_PRIVATE_KEY/APPLE_AUD."""


def is_configured() -> bool:
    return all([
        settings.APPLE_AUD,
        settings.APPLE_TEAM_ID,
        settings.APPLE_KEY_ID,
        settings.APPLE_PRIVATE_KEY,
    ])


def build_client_secret() -> str:
    """JWT ES256 firmado con la key .p8 de Sign in with Apple.

    `sub` es el bundle id (client_id), NO el team id: Apple valida que coincida
    con el client_id del form.
    """
    if not is_configured():
        raise AppleNotConfigured("faltan credenciales de Apple (TEAM_ID/KEY_ID/PRIVATE_KEY/AUD)")
    now = int(time.time())
    try:
        return jwt.encode(
            {
                "iss": settings.APPLE_TEAM_ID,
                "iat": now,
                "exp": now + CLIENT_SECRET_TTL,
                "aud": APPLE_AUDIENCE,
                "sub": settings.APPLE_AUD,
            },
            settings.APPLE_PRIVATE_KEY,
            algorithm="ES256",
            headers={"kid": settings.APPLE_KEY_ID},
        )
    except Exception as exc:  # .p8 mal pegada en la env var
        raise AppleNotConfigured(f"APPLE_PRIVATE_KEY inválida: {exc}") from exc


def _post_form(url: str, data: dict) -> dict:
    """POST application/x-www-form-urlencoded. Devuelve el JSON, o {} si vino vacío."""
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:  # noqa: S310 (url fijo)
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()[:200]
        except Exception:  # el body del error es opcional
            logger.debug("apple: HTTPError sin body legible")
        raise AppleError(f"apple respondió {exc.code}: {detail}") from exc
    except OSError as exc:  # timeout, DNS, TLS
        raise AppleError(f"no se pudo contactar a apple: {exc}") from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise AppleError("apple devolvió un body no-JSON") from exc


def exchange_code(code: str) -> str:
    """Canjea el authorization_code del login por un refresh_token."""
    payload = _post_form(APPLE_TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": settings.APPLE_AUD,
        "client_secret": build_client_secret(),
    })
    token = payload.get("refresh_token")
    if not token:
        raise AppleError(f"apple no devolvió refresh_token: {payload.get('error', 'sin detalle')}")
    return token


def revoke(token: str, token_type_hint: str = "refresh_token") -> None:
    """Revoca el token en Apple. 200 con body vacío = éxito."""
    _post_form(APPLE_REVOKE_URL, {
        "token": token,
        "token_type_hint": token_type_hint,
        "client_id": settings.APPLE_AUD,
        "client_secret": build_client_secret(),
    })
