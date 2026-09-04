import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_charts_requires_token():
    assert APIClient().post("/api/charts/", {}, format="json").status_code == 401


def test_geocode_no_requiere_token():
    """Cambió a propósito el 04-09-2026: el formulario de `/nueva` funciona sin
    cuenta y necesita resolver el lugar de nacimiento. Lo que protege este
    endpoint ya no es la sesión sino el techo por IP, que prueba
    `test_geocode_publico.py`. Sigue sin exponer nada de ninguna cuenta: busca
    en la base de GeoNames, que es pública."""
    assert APIClient().post("/api/geocode/", {"q": "x"}, format="json").status_code != 401


def test_geocode_accepts_account_token(account_client):
    resp = account_client.post("/api/geocode/", {"q": "x"}, format="json")
    assert resp.status_code not in (401, 403)


def test_interpretation_requires_token():
    assert (
        APIClient()
        .post(
            f"/api/charts/{uuid.uuid4()}/interpretation/",
            {"lang": "es"},
            format="json",
        )
        .status_code
        == 401
    )
