import uuid

import pytest
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_charts_requires_token():
    assert APIClient().post("/api/charts/", {}, format="json").status_code == 401


def test_geocode_requires_token():
    assert APIClient().post("/api/geocode/", {"q": "x"}, format="json").status_code == 401


def test_registration_is_open():
    assert APIClient().post("/api/installations/").status_code == 201


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
