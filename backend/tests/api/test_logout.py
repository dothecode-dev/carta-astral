"""Cerrar sesión invalida el token, no sólo lo olvida del lado del cliente.

Sin esto, "salir" en la web borraría la cookie pero el token seguiría sirviendo
hasta vencer, que son noventa días.
"""

import pytest
from rest_framework.test import APIClient

from api.auth import create_session
from api.models import Account, Session


@pytest.fixture
def account(db):
    return Account.objects.create(email="quien@ejemplo.test")


@pytest.mark.django_db
def test_logout_invalida_el_token(account):
    token = create_session(account)
    client = APIClient(HTTP_AUTHORIZATION=f"Bearer {token}")

    assert client.get("/api/account/").status_code == 200
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/account/").status_code == 401


@pytest.mark.django_db
def test_logout_no_toca_las_otras_sesiones(account):
    # Cerrar sesión en el navegador no puede echar a la persona de su teléfono.
    telefono = create_session(account)
    navegador = create_session(account)

    APIClient(HTTP_AUTHORIZATION=f"Bearer {navegador}").post("/api/auth/logout")

    assert APIClient(HTTP_AUTHORIZATION=f"Bearer {telefono}").get("/api/account/").status_code == 200
    assert Session.objects.filter(account=account).count() == 1


@pytest.mark.django_db
def test_logout_sin_sesion_no_entra():
    assert APIClient().post("/api/auth/logout").status_code == 401


@pytest.mark.django_db
def test_logout_dos_veces_no_explota(account):
    token = create_session(account)
    client = APIClient(HTTP_AUTHORIZATION=f"Bearer {token}")

    assert client.post("/api/auth/logout").status_code == 204
    # El segundo intento ya no tiene sesión válida: 401, no un error del servidor.
    assert client.post("/api/auth/logout").status_code == 401
