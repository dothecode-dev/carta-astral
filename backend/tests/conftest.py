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
