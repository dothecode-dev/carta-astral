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


def otorgar_derechos(account, lecturas_breves: int = 0, informes: int = 0) -> None:
    """Fondea una cuenta de test con derechos, que es la única moneda que hay.

    Los tests hablan de productos, no de saldos: `lecturas_breves` es el tier
    corto (lo que regala el alta) e `informes` el tier largo (lo que se
    compra). Antes acá se traducían los dos contadores sueltos de `Account`,
    que la migración 0025 borró.

    `external_id` incluye `account.pk`: `otorgar` es idempotente por
    external_id de forma GLOBAL (no por cuenta), así que un external_id fijo
    pisaría el otorgamiento de la segunda cuenta de un mismo test run."""
    from api.canje import otorgar

    if lecturas_breves:
        otorgar(
            account, "lectura_breve", lecturas_breves, origen="regalo",
            external_id=f"test-setup:{account.pk}:lectura_breve",
        )
    if informes:
        otorgar(
            account, "informe_natal", informes, origen="compra",
            external_id=f"test-setup:{account.pk}:informe_natal",
        )


@pytest.fixture
def make_account(db):
    """Una cuenta con los derechos que el test pida, y ninguno más.

    Sin argumentos NO otorga nada, a propósito: la mayoría de los
    `make_account()` del repo son de dominios ajenos al cobro (webhooks,
    notificaciones, sesiones, borrado) y esperan una cuenta en blanco. Quien
    necesita canjear algo lo pide explícito."""
    def _make(lecturas_breves=0, informes=0, **campos):
        from api.models import Account
        acc = Account.objects.create(**campos)
        otorgar_derechos(acc, lecturas_breves, informes)
        return acc
    return _make


@pytest.fixture
def account_client(make_account):
    from django.conf import settings

    from api.auth import create_session
    # Fondeada para los dos tiers: la mayoría de los tests que usan este
    # cliente piden tier="largo" (informe completo, canjea el derecho de
    # informe_natal) y varios el tier corto (lectura breve, canjea el de
    # lectura_breve). Sin derechos explícitos, cualquiera de los dos se
    # choca con `SinDerecho`.
    acc = make_account(lecturas_breves=settings.INSTALL_FREE_CREDITS, informes=3)
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
    # el informe completo (tier="largo") o la lectura breve (tier="corto"),
    # directo o vía HTTP.
    return make_account(lecturas_breves=settings.INSTALL_FREE_CREDITS, informes=3)


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
