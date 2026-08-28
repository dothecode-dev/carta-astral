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


@pytest.fixture
def make_account(db):
    def _make(free_balance=None, paid_balance=0):
        from django.conf import settings
        from api.models import Account
        fb = settings.INSTALL_FREE_CREDITS if free_balance is None else free_balance
        return Account.objects.create(free_balance=fb, paid_balance=paid_balance)
    return _make


@pytest.fixture
def account_client(make_account):
    from api.auth import create_session
    acc = make_account()
    token = create_session(acc)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.account = acc
    return client


@pytest.fixture
def account(make_account):
    return make_account()


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
def chart(db, account):
    from api.models import BirthData, Chart
    bd = BirthData.objects.create(date="2000-01-01", lat=0, lng=0, tz_name="UTC")
    return Chart.objects.create(birth_data=bd, data={}, engine_version="test", account=account)


@pytest.fixture
def interpretacion(db, chart, account):
    from api.models import Interpretation
    from interpret.prompts import PROMPT_VERSION

    return Interpretation.objects.create(
        chart=chart, lang="es", prompt_version=PROMPT_VERSION, text="", account=account,
    )


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
