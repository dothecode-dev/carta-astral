"""Sólo imágenes, y de tipos conocidos.

Un `.svg` o un `.html` servido desde el mismo host que la API es XSS
almacenado sobre ese origen (RF6).
"""
from importlib import reload

import pytest
from django.conf import settings
from django.test import Client
from django.urls import clear_url_caches
from wagtail.images import get_image_model
from wagtail.images.forms import get_image_form
from wagtail.images.tests.utils import get_test_image_file, get_test_image_file_svg

import config.urls


def test_solo_extensiones_de_imagen():
    permitidas = set(settings.WAGTAILIMAGES_EXTENSIONS)
    assert permitidas == {"gif", "jpg", "jpeg", "png", "webp"}
    assert "svg" not in permitidas


def test_el_media_no_vive_dentro_del_codigo():
    # Si MEDIA_ROOT queda bajo /app, el próximo deploy se lleva las imágenes:
    # el Dockerfile copia el código entero desde el builder.
    assert "/app/media" not in str(settings.MEDIA_ROOT)


@pytest.mark.django_db
def test_una_imagen_subida_se_sirve_por_http(settings, tmp_path):
    """Extremo a extremo (RF5/RF6): lo que el editor sube, el visitante lo pide y lo recibe.

    `test_api.py` verifica que la API devuelva la URL de la imagen, pero
    nunca baja el archivo. Este test sí: pega contra `/media/...`, la ruta
    que arma `config/urls.py` con `django.views.static.serve`, y confirma
    que hay bytes de verdad del otro lado.

    `config.urls` arma esa ruta con `{"document_root": settings.MEDIA_ROOT}`,
    leído UNA VEZ al importarse el módulo, no en cada request. Django resuelve
    el URLconf recién en el primer request de toda la sesión de tests y
    después reusa el módulo ya importado (mismo patrón que documenta
    `test_admin.py`): si esa primera resolución ocurre en otro test, antes de
    pisar `MEDIA_ROOT`, la ruta queda apuntando al valor real y esta prueba
    da 404 aunque el archivo exista. Recargar el módulo después de pisar
    `MEDIA_ROOT` evita depender del orden de ejecución.
    """
    try:
        settings.MEDIA_ROOT = str(tmp_path)
        reload(config.urls)
        clear_url_caches()

        imagen = get_image_model().objects.create(
            title="Rueda del cielo", file=get_test_image_file()
        )

        resp = Client().get(imagen.file.url)

        assert resp.status_code == 200
        # `serve` responde con `FileResponse` (streaming): no tiene `.content`.
        assert b"".join(resp.streaming_content)
    finally:
        # `settings` (pytest-django) ya restauró el MEDIA_ROOT real; recargar
        # de nuevo deja el módulo consistente con ese entorno para los tests
        # que corran después en la misma sesión.
        reload(config.urls)
        clear_url_caches()


@pytest.mark.django_db
def test_el_formulario_del_admin_rechaza_svg():
    """RF6 verificado donde importa de verdad: el campo del formulario de subida.

    `test_solo_extensiones_de_imagen` sólo mira `WAGTAILIMAGES_EXTENSIONS`,
    un setting que nadie obliga a usar. Quien lo lee y rechaza el archivo es
    `WagtailImageField.to_python` (`wagtail.images.fields`), así que la
    prueba real es contra el formulario que arma Wagtail para el admin.
    """
    Form = get_image_form(get_image_model())
    archivo_svg = get_test_image_file_svg()

    form = Form(data={"title": "Logo", "tags": ""}, files={"file": archivo_svg})

    assert not form.is_valid()
    assert "file" in form.errors
