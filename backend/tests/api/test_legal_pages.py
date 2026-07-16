import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_privacy_publica_sin_auth():
    resp = APIClient().get("/legal/privacy")
    assert resp.status_code == 200
    assert b"info@dothecode.com" in resp.content


@pytest.mark.django_db
def test_terms_publica_sin_auth():
    resp = APIClient().get("/legal/terms")
    assert resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("lang", "marker"),
    [("es", "Política de privacidad"), ("en", "Privacy Policy"), ("pt", "Política de privacidade")],
)
def test_privacy_en_tres_idiomas(lang, marker):
    resp = APIClient().get(f"/legal/privacy?lang={lang}")
    assert resp.status_code == 200
    assert marker in resp.content.decode()


@pytest.mark.django_db
def test_lang_invalida_cae_a_espanol():
    resp = APIClient().get("/legal/terms?lang=de")
    assert resp.status_code == 200
    assert "Términos" in resp.content.decode()


@pytest.mark.django_db
def test_terms_declara_no_consejo_y_creditos():
    body = APIClient().get("/legal/terms?lang=es").content.decode()
    assert "consejo" in body  # disclaimer IA no-consejo
    assert "crédito" in body.lower()


@pytest.mark.django_db
def test_privacy_declara_tombstone_y_procesadores():
    body = APIClient().get("/legal/privacy?lang=es").content.decode()
    assert "hash" in body.lower()  # tombstone del borrado
    assert "Anthropic" in body
    assert "RevenueCat" in body
