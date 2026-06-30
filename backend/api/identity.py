import hashlib
import secrets


def new_token() -> tuple[str, str]:
    """Devuelve (token en claro, sha256 hex). El claro sólo se entrega una vez."""
    clear = secrets.token_urlsafe(32)
    return clear, hash_token(clear)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sub_hash(provider: str, sub: str) -> str:
    """Devuelve el SHA256 hex del SSO subject (provider:sub).

    Utilizado para crear un hash anónimo del account SSO borrado,
    para que re-registración con la misma identidad no regale otro free-tier.
    """
    return hashlib.sha256(f"{provider}:{sub}".encode()).hexdigest()
