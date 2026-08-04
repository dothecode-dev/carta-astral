"""No hay ningún caso de uso de documentos: que no se pueda subir ninguno (B1).

`wagtail.documents` tiene que seguir instalado (sin él el admin de Wagtail no
arranca: ver `test_instalacion.py`), pero el formulario de subida no puede
aceptar NADA. Un `.html` o un `.svg` servido desde `/media/documents/...`,
el mismo origen donde vive la sesión del admin de Django, es XSS almacenado.

Se prueba contra el formulario real del admin (`wagtaildocs:add`), no sólo
contra el setting: lo que hace falta es que Wagtail rechace el archivo al
validar el modelo (`AbstractDocument.clean()`, que lee
`WAGTAILDOCS_EXTENSIONS`), y eso sólo se ve pegándole a la view de verdad.
"""
from importlib import reload

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import clear_url_caches, reverse
from wagtail.documents import get_document_model
from wagtail.documents.forms import get_document_form

import config.urls

User = get_user_model()


@pytest.fixture
def admin_montado(monkeypatch, settings, tmp_path):
    """Monta el admin de Wagtail bajo un slug fijo y loguea a un superusuario.

    Mismo patrón que `test_admin.py`: `config.urls` arma `urlpatterns` una
    sola vez al importarse leyendo `WAGTAIL_ADMIN_URL` del entorno, así que
    hace falta recargar el módulo con el entorno modificado.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    try:
        with monkeypatch.context() as m:
            m.setenv("WAGTAIL_ADMIN_URL", "panel-notas")
            reload(config.urls)
            clear_url_caches()

            staff = User.objects.create_superuser("staff", "s@x.com", "pw-de-test-12345")
            c = Client()
            # force_login: ver comentario en tests/api/test_admin.py sobre axes.
            c.force_login(staff)
            yield c
    finally:
        reload(config.urls)
        clear_url_caches()


def _sube(client, filename, contenido, content_type):
    archivo = SimpleUploadedFile(filename, contenido, content_type=content_type)
    return client.post(
        reverse("wagtaildocs:add"),
        {"title": filename, "file": archivo},
    )


@pytest.mark.django_db
def test_se_rechaza_un_html_con_script(admin_montado):
    resp = _sube(
        admin_montado,
        "payload.html",
        b"<script>alert(document.cookie)</script>",
        "text/html",
    )

    # Redirect (302) significa que Wagtail lo aceptó y guardó: eso es el bug.
    assert resp.status_code == 200
    assert "file" in resp.context["form"].errors
    assert get_document_model().objects.count() == 0


@pytest.mark.django_db
def test_se_rechaza_un_svg_con_script(admin_montado):
    resp = _sube(
        admin_montado,
        "payload.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        "image/svg+xml",
    )

    assert resp.status_code == 200
    assert "file" in resp.context["form"].errors
    assert get_document_model().objects.count() == 0


@pytest.mark.django_db
def test_se_rechaza_un_pdf(admin_montado):
    """Un PDF no es XSS, pero la decisión del dueño es que NINGÚN documento
    tiene caso de uso en este CMS: notas de blog, texto e imágenes."""
    resp = _sube(
        admin_montado,
        "informe.pdf",
        b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n",
        "application/pdf",
    )

    assert resp.status_code == 200
    assert "file" in resp.context["form"].errors
    assert get_document_model().objects.count() == 0


@pytest.mark.django_db
def test_se_rechaza_tambien_por_el_subidor_multiple(admin_montado):
    """El admin de Wagtail tiene un segundo camino para subir documentos: el
    subidor múltiple (arrastrar y soltar), que pega a otra vista
    (`wagtaildocs:add_multiple`, JSON/AJAX) pero valida con el mismo
    `ModelForm`. Si sólo se prueba `wagtaildocs:add`, ese segundo camino
    podría quedar sin cubrir."""
    archivo = SimpleUploadedFile(
        "payload.html", b"<script>alert(1)</script>", content_type="text/html"
    )

    resp = admin_montado.post(
        reverse("wagtaildocs:add_multiple"),
        {"title": "payload.html", "files[]": archivo},
    )

    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert get_document_model().objects.count() == 0


@pytest.mark.django_db
def test_el_formulario_del_admin_rechaza_cualquier_extension():
    """La misma prueba que `test_imagenes.py` hace para imágenes, pero
    contra el formulario de documentos: verificalo donde importa de verdad,
    en el campo que Wagtail arma para el admin."""
    Form = get_document_form(get_document_model())
    archivo = SimpleUploadedFile("payload.html", b"<script>1</script>", content_type="text/html")

    form = Form(data={"title": "Payload", "tags": ""}, files={"file": archivo})

    assert not form.is_valid()
    assert "file" in form.errors
