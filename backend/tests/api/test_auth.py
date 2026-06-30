import pytest
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory

from api.auth import InstallationTokenAuthentication
from api.identity import new_token
from api.models import Installation

pytestmark = pytest.mark.django_db


def test_valid_bearer_resolves_installation():
    clear, h = new_token()
    inst = Installation.objects.create(token_hash=h)
    req = APIRequestFactory().get("/api/installations/me/", HTTP_AUTHORIZATION=f"Bearer {clear}")
    user, auth = InstallationTokenAuthentication().authenticate(req)
    assert auth.id == inst.id


def test_missing_header_returns_none():
    req = APIRequestFactory().get("/api/installations/me/")
    assert InstallationTokenAuthentication().authenticate(req) is None


def test_bad_token_raises():
    req = APIRequestFactory().get("/", HTTP_AUTHORIZATION="Bearer nope")
    with pytest.raises(AuthenticationFailed):
        InstallationTokenAuthentication().authenticate(req)
