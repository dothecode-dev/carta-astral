"""Sólo imágenes, y de tipos conocidos.

Un `.svg` o un `.html` servido desde el mismo host que la API es XSS
almacenado sobre ese origen (RF6).
"""
from django.conf import settings


def test_solo_extensiones_de_imagen():
    permitidas = set(settings.WAGTAILIMAGES_EXTENSIONS)
    assert permitidas == {"gif", "jpg", "jpeg", "png", "webp"}
    assert "svg" not in permitidas


def test_el_media_no_vive_dentro_del_codigo():
    # Si MEDIA_ROOT queda bajo /app, el próximo deploy se lleva las imágenes:
    # el Dockerfile copia el código entero desde el builder.
    assert "/app/media" not in str(settings.MEDIA_ROOT)
