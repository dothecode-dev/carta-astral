"""La API del CMS la consume el frontend en el build: es pública y de lectura.

`REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES` es `HasAccount` y es global: sin
`AllowAny` explícito, esta API devolvería 401 a todo el mundo, incluido el
frontend (RF3).
"""
import pytest
from rest_framework.test import APIClient
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Locale, Site

from cms.models import NoteIndexPage, NotePage


@pytest.fixture
def nota_publicada(db):
    # La API filtra por descendientes del `root_page` del Site (RF3): colgar
    # la nota de la raíz real del árbol (`depth=1`) la deja fuera de ese
    # filtro y la API nunca la encuentra, aunque esté publicada.
    raiz = Site.objects.get(is_default_site=True).root_page
    indice = NoteIndexPage(title="Notas", slug="notas")
    raiz.add_child(instance=indice)
    nota = NotePage(
        title="Sol, Luna y Ascendente",
        slug="sol-luna-ascendente",
        fecha="2026-07-14",
        bajada="Los tres que no son lo mismo.",
        cuerpo="<p>El Sol es lo que quiere ser.</p>",
        live=True,
    )
    indice.add_child(instance=nota)
    return nota


@pytest.fixture
def nota_con_portada(nota_publicada, settings, tmp_path):
    # `MEDIA_ROOT` apunta a un directorio temporal: generar la rendition real
    # escribe un archivo en disco, y no queremos que caiga en el repo.
    settings.MEDIA_ROOT = str(tmp_path)
    Image = get_image_model()
    imagen = Image.objects.create(
        title="Rueda del cielo", file=get_test_image_file(size=(3200, 2000))
    )
    nota_publicada.portada = imagen
    nota_publicada.save()
    return nota_publicada


@pytest.mark.django_db
def test_responde_sin_autenticacion(nota_publicada):
    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage")
    assert resp.status_code == 200
    assert resp.json()["meta"]["total_count"] == 1


@pytest.mark.django_db
def test_un_borrador_no_aparece(nota_publicada):
    nota_publicada.live = False
    nota_publicada.save()
    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage")
    assert resp.json()["meta"]["total_count"] == 0


@pytest.mark.django_db
@pytest.mark.parametrize("verbo", ["post", "put", "patch", "delete"])
def test_no_se_puede_escribir(verbo, nota_publicada):
    resp = getattr(APIClient(), verbo)("/cms/api/v2/pages/")
    assert resp.status_code == 405


@pytest.mark.django_db
def test_los_campos_declarados_viajan_en_la_respuesta(nota_publicada):
    """No alcanza con declarar `api_fields`: hay que ver que el JSON los traiga."""
    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&fields=*")
    item = resp.json()["items"][0]
    assert item["fecha"] == "2026-07-14"
    assert item["bajada"] == "Los tres que no son lo mismo."
    assert item["cuerpo"] == "<p>El Sol es lo que quiere ser.</p>"
    assert item["portada"] is None


@pytest.mark.django_db
def test_el_cuerpo_expande_imagen_y_enlace_interno(nota_publicada, settings, tmp_path):
    """El caso que se le escapó a `test_los_campos_declarados_viajan_en_la_respuesta`,
    que sólo usa un `<p>` plano.

    Wagtail guarda el cuerpo en un formato interno
    (`<a linktype="page" id="3">`, `<embed embedtype="image" id="1" .../>`):
    sin expandirlo, la API devolvería ese crudo y la primera nota con una
    imagen o un enlace interno saldría rota en la web. La API tiene que
    devolver HTML ya expandido y usable (`<img src="...">`, `<a href="...">`).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    Image = get_image_model()
    imagen = Image.objects.create(title="Rueda del cielo", file=get_test_image_file())
    indice = nota_publicada.get_parent()

    nota_publicada.cuerpo = (
        f'<p>Ver el <a linktype="page" id="{indice.id}">índice</a></p>'
        f'<embed embedtype="image" id="{imagen.id}" format="left" alt="Rueda"/>'
    )
    nota_publicada.save()

    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&fields=*")
    cuerpo = resp.json()["items"][0]["cuerpo"]

    assert "<img" in cuerpo and 'src="' in cuerpo
    assert "<a href=" in cuerpo
    # El formato interno no debe sobrevivir a la expansión.
    assert "linktype=" not in cuerpo
    assert "embedtype=" not in cuerpo


@pytest.mark.django_db
def test_una_nota_de_otro_idioma_no_aparece(nota_publicada):
    """RF4: cada idioma es una página aparte y la API filtra por `?locale=`.

    El frontend arma cada idioma con su propio pedido a la API: si pide
    `?locale=en` no puede recibir una nota que sólo existe en español.
    """
    locale_en = Locale.objects.get(language_code="en")
    nota_publicada.copy_for_translation(locale_en, copy_parents=True)

    resp_es = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&locale=es")
    assert resp_es.json()["meta"]["total_count"] == 1

    resp_en = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&locale=en")
    # La copia en inglés nace en borrador (`copy_for_translation` no publica):
    # no debería aparecer todavía.
    assert resp_en.json()["meta"]["total_count"] == 0


@pytest.mark.django_db
def test_la_portada_trae_las_dos_renditions(nota_con_portada):
    """El frontend necesita una URL de imagen usable, no el original sin redimensionar.

    `portada` (el FK crudo) sólo trae id/meta/title: no sirve para pintar nada.
    `portada_tarjeta` y `portada_cabecera` son la misma imagen ya redimensionada,
    con URL, ancho y alto listos para un `<img>`.
    """
    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&fields=*")
    item = resp.json()["items"][0]

    tarjeta = item["portada_tarjeta"]
    assert tarjeta["width"] == 640
    assert tarjeta["height"] == 400
    assert tarjeta["url"]

    cabecera = item["portada_cabecera"]
    assert cabecera["width"] == 1600
    # La fuente es 3200x2000 (relación 16:10): escalar el ancho a 1600 sin
    # recortar da 1000 de alto.
    assert cabecera["height"] == 1000
    assert cabecera["url"]


@pytest.mark.django_db
def test_imagenes_responde_sin_autenticacion(nota_con_portada):
    resp = APIClient().get("/cms/api/v2/images/")
    assert resp.status_code == 200
    assert resp.json()["meta"]["total_count"] == 1


@pytest.mark.django_db
@pytest.mark.parametrize("verbo", ["post", "put", "patch", "delete"])
def test_imagenes_no_se_puede_escribir(verbo, nota_con_portada):
    resp = getattr(APIClient(), verbo)("/cms/api/v2/images/")
    assert resp.status_code == 405
