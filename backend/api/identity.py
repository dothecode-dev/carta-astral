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


def normalizar(email: str) -> str:
    """Minúsculas y trim, nada más. Sacar los puntos de Gmail está mal para
    cualquier otro proveedor y es un pozo sin fondo.

    Vive acá y no en `codigos_acceso.py` (donde nació) porque `accounts.py`
    (C3, revisión de `puertas-de-acceso`) también la necesita: sin normalizar
    en un único lugar para las tres puertas de entrada (mail, Google, Apple),
    la misma dirección en otro casing termina en cuentas distintas cuando el
    proveedor SSO no la manda en minúsculas (gmail.com sí; un dominio
    Workspace no)."""
    return email.strip().lower()


def config_faltante() -> list[str]:
    """Nombres de las variables de configuración de identidad que faltan.

    Control compensatorio del Ruling 7: el fail-fast de arranque (RF8) se
    cambió por un log en stderr para no tumbar todo el backend —informes
    pagos incluidos— por una variable de una sola superficie (el login por
    mail). Pero un log que nadie lee y que `make deploy` no mira no avisa de
    nada: esto es lo que `EstadoView` (`api/mantenimiento.py`) expone en
    `GET /api/estado/`, que la web ya sondea y que `make deploy` ya consulta
    en cada despliegue. Sin filtrar valores, sólo qué falta.
    """
    faltantes = []
    if not tombstone_hmac_configurada():
        faltantes.append("TOMBSTONE_HMAC_KEY")
    return faltantes


def tombstone_hmac_configurada() -> bool:
    """Si `TOMBSTONE_HMAC_KEY` está seteada, sin levantar `ImproperlyConfigured`.

    Existe para que quien va a llamar a `sub_hash("email", ...)` pueda
    preguntar ANTES de hacerlo (C2, revisión de `puertas-de-acceso`): sin
    esto, la única forma de enterarse era capturar la excepción después de
    haber tocado algo que ya no se podía deshacer —el código de acceso
    marcado como usado en `CanjearCodigoView`, por ejemplo—.
    """
    return bool(settings.TOMBSTONE_HMAC_KEY)


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
    if not tombstone_hmac_configurada():
        # `settings.TOMBSTONE_HMAC_KEY` ya trae un valor fijo de desarrollo
        # cuando DEBUG está prendido (ver config/settings.py): si llegó vacía
        # acá es porque de verdad no hay clave configurada, en producción.
        raise ImproperlyConfigured(
            "TOMBSTONE_HMAC_KEY es obligatoria: sin ella el tombstone de mail "
            "no protege el regalo de bienvenida."
        )
    clave = settings.TOMBSTONE_HMAC_KEY
    return hmac.new(clave.encode(), material, hashlib.sha256).hexdigest()
