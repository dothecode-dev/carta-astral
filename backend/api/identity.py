import hashlib
import secrets


def new_token() -> tuple[str, str]:
    """Devuelve (token en claro, sha256 hex). El claro sólo se entrega una vez."""
    clear = secrets.token_urlsafe(32)
    return clear, hash_token(clear)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
