"""La API del CMS la consume el frontend en el build: es pública y de lectura.

`REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES` es `HasAccount` y es global: sin
`AllowAny` explícito, esta API devolvería 401 a todo el mundo, incluido el
frontend (RF3).
"""
from pathlib import Path

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

    No alcanza con verificar que la etiqueta exista (ronda 1 de la revisión
    final): hay que verificar A DÓNDE apunta. Este backend es headless
    (`config/urls.py` nunca monta `wagtail.urls`), así que Wagtail no tiene
    ninguna URL propia para resolver una página; sin `cms/wagtail_hooks.py`
    el `href` sale literalmente como el string "None". Se prueba contra un
    enlace al índice (`NoteIndexPage`) Y contra un enlace a una nota
    (`NotePage`): son dos tipos de página con URLs distintas.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    settings.WEB_BASE_URL = "https://cartaastral.app"
    Image = get_image_model()
    imagen = Image.objects.create(title="Rueda del cielo", file=get_test_image_file())
    indice = nota_publicada.get_parent()

    nota_publicada.cuerpo = (
        f'<p>Ver el <a linktype="page" id="{indice.id}">índice</a> '
        f'o <a linktype="page" id="{nota_publicada.id}">esta nota</a></p>'
        f'<embed embedtype="image" id="{imagen.id}" format="left" alt="Rueda"/>'
    )
    nota_publicada.save()

    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&fields=*")
    cuerpo = resp.json()["items"][0]["cuerpo"]

    # El formato interno no debe sobrevivir a la expansión.
    assert "linktype=" not in cuerpo
    assert "embedtype=" not in cuerpo
    assert "None" not in cuerpo

    # El enlace a la nota vive en la web (RichTextAPIField headless), con el
    # esquema de rutas /notas ya decidido para el frontend (spec del CMS).
    assert f'<a href="https://cartaastral.app/es/notas/{nota_publicada.slug}">' in cuerpo
    # El enlace al índice, sin slug: es la portada del listado en la web.
    assert '<a href="https://cartaastral.app/es/notas">' in cuerpo

    # La imagen embebida usa la URL absoluta (WAGTAILADMIN_BASE_URL), igual
    # que portada_tarjeta/portada_cabecera: si la web vive en otro dominio,
    # una URL relativa al backend rompe la imagen.
    assert f'src="{settings.WAGTAILADMIN_BASE_URL}/media/' in cuerpo
    assert 'src="/media/' not in cuerpo


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
def test_el_endpoint_de_imagenes_no_existe(nota_con_portada):
    """`ImagesAPIViewSet` no filtra por publicación y estaba montado con AllowAny.

    Sólo excluye colecciones con `CollectionViewRestriction`, y la colección
    Root que Wagtail crea por defecto no tiene ninguna: el endpoint listaba
    TODAS las imágenes subidas con su `title` y su `download_url`, así que la
    portada de una nota todavía en borrador —con el título del artículo en el
    campo `title`— quedaba pública antes de publicar la nota. La web no lo
    necesita: las portadas viajan resueltas dentro de la respuesta de páginas.
    """
    nota_con_portada.live = False
    nota_con_portada.save()

    resp = APIClient().get("/cms/api/v2/images/")

    assert resp.status_code == 404


@pytest.mark.django_db
def test_un_bearer_vencido_no_convierte_la_api_publica_en_401(nota_publicada):
    """El `AllowAny` sólo desactiva el permiso, no la autenticación.

    `DEFAULT_AUTHENTICATION_CLASSES` del proyecto es `AccountTokenAuthentication`
    y DRF la corre ANTES del permiso: un `Authorization` con un token vencido
    levanta `AuthenticationFailed`, que propaga aunque el permiso sea AllowAny.
    La web de fase 2 es un cliente logueado; si reusa su cliente HTTP con el
    token guardado, el blog público dejaría de renderizar apenas expire.
    """
    resp = APIClient().get(
        "/cms/api/v2/pages/?type=cms.NotePage", HTTP_AUTHORIZATION="Bearer token-vencido"
    )

    assert resp.status_code == 200
    assert resp.json()["meta"]["total_count"] == 1


@pytest.mark.django_db
def test_una_imagen_sin_archivo_no_tumba_la_nota_entera(nota_publicada, settings, tmp_path):
    """El escenario que advierte el Dockerfile: deploy sin el volumen montado.

    Las filas de `Image` quedan en la base y los archivos no están en
    MEDIA_ROOT. `image.get_rendition()` levanta `SourceImageIOError`, que sale
    de `expand_db_html` y hace responder 500 a la nota COMPLETA, no sólo a esa
    imagen. Wagtail de stock degrada a un placeholder roto; el handler propio
    tiene que hacer lo mismo.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    Image = get_image_model()
    imagen = Image.objects.create(title="Rueda", file=get_test_image_file())
    # El deploy que se lleva /data/media: la fila sigue, el archivo no.
    Path(imagen.file.path).unlink()

    nota_publicada.cuerpo = f'<embed embedtype="image" id="{imagen.id}" format="left" alt="R"/>'
    nota_publicada.save()

    resp = APIClient().get("/cms/api/v2/pages/?type=cms.NotePage&fields=*")

    assert resp.status_code == 200
    assert "<img" in resp.json()["items"][0]["cuerpo"]


@pytest.mark.django_db
def test_los_enlaces_internos_de_una_nota_traducida_apuntan_a_su_idioma(
    nota_publicada, settings
):
    """`copy_for_translation` copia el cuerpo tal cual, con el id de la página ES.

    O sea que el `<a linktype="page" id="...">` de la nota en inglés sigue
    apuntando a la fila española. Resolver la URL con el locale de esa fila
    mandaba al lector inglés al artículo en español; hay que resolver contra
    la traducción (`.localized`) en el idioma de la nota que se serializa.
    """
    settings.WEB_BASE_URL = "https://cartaastral.app"
    otra = NotePage(
        title="Mercurio retrógrado",
        slug="mercurio-retrogrado",
        fecha="2026-07-20",
        bajada="No se rompe nada.",
        cuerpo="<p>Nada.</p>",
        live=True,
    )
    nota_publicada.get_parent().add_child(instance=otra)
    nota_publicada.cuerpo = f'<p><a linktype="page" id="{otra.id}">la otra</a></p>'
    nota_publicada.save()

    locale_en = Locale.objects.get(language_code="en")
    otra_en = otra.copy_for_translation(locale_en, copy_parents=True)
    otra_en.slug = "mercury-retrograde"
    otra_en.save_revision().publish()
    nota_en = nota_publicada.copy_for_translation(locale_en)
    nota_en.slug = "sun-moon-ascendant"
    nota_en.save_revision().publish()

    resp = APIClient().get(
        "/cms/api/v2/pages/?type=cms.NotePage&locale=en&slug=sun-moon-ascendant&fields=*"
    )
    cuerpo = resp.json()["items"][0]["cuerpo"]

    assert '<a href="https://cartaastral.app/en/notas/mercury-retrograde">' in cuerpo
    assert "/es/notas/" not in cuerpo
