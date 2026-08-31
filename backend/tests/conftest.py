import pytest
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _static_sin_manifest(settings):
    """Los tests no dependen de haber corrido `collectstatic`.

    En producción el static se sirve con `CompressedManifestStaticFilesStorage`,
    que resuelve cada `{% static %}` contra `staticfiles/staticfiles.json` y
    revienta con ValueError si el archivo no está en el manifest. Los tests que
    le pegan a las views del admin de Wagtail renderizan plantillas que piden
    `wagtailadmin/css/core.css`, así que sin manifest fallaban.

    En una máquina de desarrollo el fallo no se ve —`staticfiles/` quedó de
    algún `collectstatic` anterior y el manifest existe—, pero el CI arranca de
    un checkout limpio y ahí fallaba siempre. Lo que se está probando es el
    rechazo de un documento, no cómo se sirve el CSS del admin: en tests alcanza
    el storage plano, que devuelve la URL sin consultar el manifest.
    """
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }


def otorgar_derechos_de_balance(account, free_balance, paid_balance: int) -> None:
    """Traduce `free_balance`/`paid_balance` a los derechos equivalentes (Task 11).

    Desde que `interpretation_service` cobra por capacidad (`canje.canjear`)
    en vez de por lote (`ledger.charge`), una cuenta fondeada sólo con los
    campos viejos no tiene con qué canjear nada — `canjear` levanta
    `SinDerecho` aunque `free_balance`/`paid_balance` sean positivos. Los
    campos viejos siguen existiendo (Task 13 los borra) y los test que
    fondean cuentas con ellos siguen valiendo como forma de pedir "esta
    cuenta puede leer N breves y M informes completos" — esto es lo que
    hace ese pedido cierto también en el modelo nuevo, sin tener que tocar
    cada test uno por uno.

    `free_balance=None` (o `0`) y `paid_balance=0` NO otorgan nada — a
    propósito: la inmensa mayoría de los `make_account()` del repo son de
    dominios ajenos al cobro de interpretaciones (canje, webhooks, IAP,
    notificaciones) y esperan una cuenta SIN derechos previos, sólo con el
    campo viejo en su default. Que la traducción sea un no-op sobre el
    default es lo que evita que este helper les invente un `Derecho` que
    esos tests no pidieron y no esperan (ver `make_account`).

    `external_id` incluye `account.pk`: `otorgar` es idempotente por
    external_id de forma GLOBAL (no por cuenta), así que un external_id fijo
    pisaría el otorgamiento de la segunda cuenta de un mismo test run."""
    from api.canje import otorgar

    if free_balance:
        otorgar(
            account, "lectura_breve", free_balance, origen="regalo",
            external_id=f"test-setup:{account.pk}:lectura_breve",
        )
    if paid_balance:
        otorgar(
            account, "informe_natal", paid_balance, origen="compra",
            external_id=f"test-setup:{account.pk}:informe_natal",
        )


@pytest.fixture
def make_account(db):
    def _make(free_balance=None, paid_balance=0):
        from django.conf import settings
        from api.models import Account
        fb = settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
        acc = Account.objects.create(free_balance=fb, paid_balance=paid_balance)
        # Se traduce el `free_balance` PEDIDO (`free_balance`, antes de
        # resolver el default), no el que terminó en la fila (`fb`): un
        # `make_account()` a secas no pide nada en particular —la mayoría de
        # los tests del repo son así, y de dominios que no cobran
        # interpretaciones— así que no le otorgamos un derecho que nunca
        # pidió sólo porque el campo viejo cae en un default no-cero. Quien
        # sí lo quiere lo pide explícito (`account`/`account_client` abajo).
        otorgar_derechos_de_balance(acc, free_balance, paid_balance)
        return acc
    return _make


@pytest.fixture
def account_client(make_account):
    from django.conf import settings

    from api.auth import create_session
    # paid_balance=3, igual que el free_balance que ya trae make_account()
    # por default (INSTALL_FREE_CREDITS): la mayoría de los tests de este
    # archivo piden tier="largo" (informe completo), que se cobra del lote
    # paid (RF9), no del free — sin esto, cualquier test que postee al
    # endpoint con tier="largo" sin fondear paid_balance explícito se choca
    # con QuotaExceeded("paid"). free_balance explícito (Task 11): sin
    # pasarlo, `make_account` no traduce el default a un derecho de
    # lectura_breve (ver su docstring) y un test que pida tier="corto" se
    # choca con `SinDerecho` aunque el campo viejo esté en positivo.
    acc = make_account(free_balance=settings.INSTALL_FREE_CREDITS, paid_balance=3)
    token = create_session(acc)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.account = acc
    return client


@pytest.fixture
def account(make_account):
    from django.conf import settings

    # Mismo motivo que `account_client`: `chart`/`interpretacion`/
    # `client_autenticado` cuelgan de esta cuenta y varios tests ejercitan
    # el informe completo (tier="largo" ⇒ lote paid) o la lectura breve
    # (tier="corto" ⇒ lote free) directo o vía HTTP.
    return make_account(free_balance=settings.INSTALL_FREE_CREDITS, paid_balance=3)


@pytest.fixture
def client_autenticado(account):
    """Como `account_client`, pero sobre la cuenta del fixture `account` en vez
    de crear una propia: así comparte cuenta con `chart`/`interpretacion`, que
    dependen de `account`."""
    from api.auth import create_session
    token = create_session(account)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def make_chart(db):
    def _make(account):
        from api.models import BirthData, Chart
        bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
        return Chart.objects.create(birth_data=bd, data={}, engine_version="test", account=account)
    return _make


@pytest.fixture
def chart(make_chart, account):
    return make_chart(account=account)


@pytest.fixture
def interpretacion(db, chart, account):
    from api.models import Interpretation
    from interpret.prompts import PROMPT_VERSION

    return Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )


@pytest.fixture
def interpretacion_completa(db, chart, account):
    """Un informe terminado, con las ocho secciones ya escritas.

    `chart.data` es `{}`, así que `time_known` cae en el default de
    `secciones_aplicables` (`True`): las ocho secciones del catálogo aplican,
    incluida "casas"."""
    from api.models import Interpretation, InterpretationSection
    from interpret.prompts import PROMPT_VERSION, SECCIONES

    interpretacion = Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, account=account, completa=True,
    )
    for orden, seccion in enumerate(SECCIONES):
        InterpretationSection.objects.create(
            interpretation=interpretacion, slug=seccion.slug, orden=orden,
            texto=f"Texto de la sección {seccion.slug}.",
        )
    return interpretacion


@pytest.fixture
def db_cache(settings, db):
    """Corre un test contra `DatabaseCache`, el backend real de producción.

    `make test-back` y `make test-back-pg` usan LocMem por default (no
    exportan `USE_DB_CACHE`): ahí `touch()` chequea expiración antes de
    tocar la clave y cualquier test de locking pasa por una razón que no es
    la real. `DatabaseCache` no hace ese chequeo en `touch()` — sólo en
    `add()` — así que es el único backend donde un bug de lock resucitado
    se puede ver fallar. Usar este fixture en cualquier test que ejercite
    `interp:lock:*` (tomar, renovar o soltar).
    """
    from django.core.cache import cache
    from django.core.management import call_command

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "django_cache",
        }
    }
    call_command("createcachetable")
    cache.clear()
    yield cache
    cache.clear()
