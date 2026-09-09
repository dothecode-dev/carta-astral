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
    """Nombres de las variables de configuración que faltan PARA EL LOGIN POR
    MAIL. Hoy es una sola: `TOMBSTONE_HMAC_KEY`.

    El nombre sugiere algo más amplio ("identidad") de lo que esta función
    en realidad mira, y eso era mentira desde el vamos (Hallazgo 4 de la
    re-revisión de `puertas-de-acceso`): Google y Apple, sin `GOOGLE_AUD` o
    `APPLE_AUD`/`APPLE_TEAM_ID`/`APPLE_KEY_ID`/`APPLE_PRIVATE_KEY`, se
    quedan mal configurados igual y `GET /api/estado/` sigue diciendo que
    está todo bien. No es un descuido silencioso: esas dos puertas YA
    fallan cerradas por su cuenta, cada una en su propio punto de uso
    (`api/sso.py::_validate` levanta `SSONotConfigured` si `audiences_for()`
    da vacío; `api/apple.py::build_client_secret` levanta
    `AppleNotConfigured`), así que
    un login mal configurado por Google o Apple ya da 401/503 en el
    momento, sin necesitar que este endpoint lo anuncie de antemano. Lo que
    a ESTA función le falta cubrir es sólo el login por mail: sin
    `TOMBSTONE_HMAC_KEY` el backend arranca igual (no hay fail-fast de RF8,
    a propósito) y sin este chequeo el único aviso quedaba en un log de
    arranque que nadie mira.

    Control compensatorio del Ruling 7: esto es lo que `EstadoView`
    (`api/mantenimiento.py`) expone en `GET /api/estado/`, que la web ya
    sondea y que `make deploy` ya consulta en cada despliegue. Sin filtrar
    valores, sólo qué falta.
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
