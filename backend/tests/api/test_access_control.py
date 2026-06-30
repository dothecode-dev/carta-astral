import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_charts_requires_token():
    assert APIClient().post("/api/charts/", {}, format="json").status_code == 401


def test_geocode_requires_token():
    assert APIClient().post("/api/geocode/", {"q": "x"}, format="json").status_code == 401


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
