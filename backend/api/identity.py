import hashlib
import hmac
import secrets

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def new_token() -> tuple[str, str]:
    """Devuelve (token en claro, sha256 hex). El claro sólo se entrega una vez."""
    clear = secrets.token_urlsafe(32)
    return clear, hash_token(clear)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sub_hash(provider: str, sub: str) -> str:
    """SHA256 hex del SSO subject (provider:sub), para el tombstone del free-tier.

    Para apple y google el `sub` es un id opaco del proveedor: el sha256 pelado
    ya es anónimo. Para `email` el `sub` ES la dirección, y un sha256 lo revierte
    cualquiera con una lista de mails, así que ahí va HMAC con clave del
    servidor. Los hashes de apple y google no cambian: los tombstones que ya
    están en producción tienen que seguir matcheando.
    """
    material = f"{provider}:{sub}".encode()
    if provider != "email":
        return hashlib.sha256(material).hexdigest()
    clave = settings.TOMBSTONE_HMAC_KEY
    if not clave:
        # `settings.TOMBSTONE_HMAC_KEY` ya trae un valor fijo de desarrollo
        # cuando DEBUG está prendido (ver config/settings.py): si llegó vacía
        # acá es porque de verdad no hay clave configurada, en producción.
        raise ImproperlyConfigured(
            "TOMBSTONE_HMAC_KEY es obligatoria: sin ella el tombstone de mail "
            "no protege el regalo de bienvenida."
        )
    return hmac.new(clave.encode(), material, hashlib.sha256).hexdigest()
