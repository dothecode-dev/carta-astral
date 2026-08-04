"""El idioma de una respuesta de `/api/` lo decide el cliente, no el CMS.

`LANGUAGE_CODE` pasó de 'en-us' a 'es' porque Wagtail lo usa como locale por
defecto del contenido, pero el setting es global: sin `LocaleMiddleware`, el
idioma activo era 'es' para toda request y los mensajes traducibles de
Django/DRF (el `detail` de un 401, un 405, un 429) salían en español para la
app en inglés y para la app en portugués. La app manda su idioma en
`Accept-Language`; esto verifica que el backend lo respete.
"""
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_sin_token_el_error_sale_en_el_idioma_del_cliente():
    resp = APIClient().get("/api/charts/", HTTP_ACCEPT_LANGUAGE="en")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authentication credentials were not provided."


@pytest.mark.django_db
def test_el_mismo_error_en_portugues():
    resp = APIClient().get("/api/charts/", HTTP_ACCEPT_LANGUAGE="pt-BR")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "As credenciais de autenticação não foram fornecidas."


@pytest.mark.django_db
def test_sin_accept_language_cae_al_idioma_por_defecto():
    """El fallback sigue siendo `LANGUAGE_CODE`, que el CMS necesita en 'es'."""
    resp = APIClient().get("/api/charts/")

    assert resp.status_code == 401
    assert resp.json()["detail"] == "Las credenciales de autenticación no se proveyeron."
