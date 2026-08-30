import pytest
from django.conf import settings
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_account_me_returns_credits():
    from api.auth import create_session
    from api.models import Account

    acc = Account.objects.create()
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = c.get("/api/account/")
    assert resp.status_code == 200
    assert resp.data["credits_available"] == settings.INSTALL_FREE_CREDITS
    assert resp.data["account_id"] == acc.id


@pytest.mark.django_db
def test_la_cuenta_separa_lecturas_gratis_de_informes_pagos(make_account):
    """`credits_available` (la suma) dejó de significar algo: alguien con 0 free
    y 1 paid "tiene créditos" y no puede pedir una lectura breve. El endpoint
    debe devolver los dos números por separado."""
    from api.auth import create_session

    # Crear cuenta con valores distintos en cada lote para verificar que
    # el endpoint no confunde los números
    acc = make_account(free_balance=5, paid_balance=2)
    token = create_session(acc)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    datos = c.get("/api/account/").json()
    assert datos["free_credits"] == 5
    assert datos["paid_credits"] == 2
    # La suma debe estar presente por compatibilidad con la app RN apagada
    assert datos["credits_available"] == 7
