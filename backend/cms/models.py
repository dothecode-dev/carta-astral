"""Las páginas del CMS. Sólo contenido: acá no entra nada de la aplicación."""

from datetime import date

from django.db import models
from django.utils import translation
from rest_framework.fields import Field
from wagtail.admin.panels import FieldPanel
from wagtail.api import APIField
from wagtail.fields import RichTextField
from wagtail.images.api.fields import ImageRenditionField
from wagtail.models import Page
from wagtail.rich_text import expand_db_html


class RichTextAPIField(Field):
    """Expande el formato interno de un `RichTextField` a HTML usable.

    Wagtail guarda el cuerpo en un formato propio (`<a linktype="page"
    id="3">`, `<embed embedtype="image" id="1" format="left" alt="T"/>`) y
    sólo lo expande a HTML real (`<a href>`, `<img src>`) en las plantillas,
    vía el tag `{% richtext %}`. La API v2 no lo hace sola: sin este campo,
    `cuerpo` viajaría crudo y la primera nota con una imagen o un enlace
    interno saldría rota en la web.

    La expansión corre con el idioma de la nota activo porque los enlaces
    internos se resuelven con `.localized` (`cms/wagtail_hooks.py`), que mira
    el idioma activo y no el de la página enlazada: sin esto, los enlaces de
    una nota traducida apuntarían a la versión en español.
    """

    def get_attribute(self, instance):
        # La página entera, no sólo el texto: `to_representation` necesita
        # saber en qué idioma está la nota, y el valor del campo no lo dice.
        return (instance, super().get_attribute(instance))

    def to_representation(self, data):
        pagina, value = data
        with translation.override(pagina.locale.language_code):
            return expand_db_html(value)


class NoteIndexPage(Page):
    """El listado de notas. Existe para colgar las notas de algún lado."""

    subpage_types = ["cms.NotePage"]

    # Uno por idioma, no uno en total. `max_count = 1` (lo que había acá) es
    # global: `Page.can_create_at` hace `cls.objects.count() < cls.max_count`
    # sin filtrar por locale, así que creado el índice en español el admin ya
    # no dejaba crear el de inglés ni el de portugués —y como las notas cuelgan
    # sólo de un índice (`NotePage.parent_page_types`), esos dos idiomas se
    # quedaban sin ninguna nota posible.
    @classmethod
    def can_create_at(cls, parent):
        if not super().can_create_at(parent):
            return False
        return not cls.objects.filter(locale=parent.locale).exists()

    bajada = models.CharField(max_length=255, blank=True)

    content_panels = Page.content_panels + [FieldPanel("bajada")]


class NotePage(Page):
    """Una nota del blog.

    Cada idioma es una página aparte, con su propio slug y su propio estado de
    publicación: se puede publicar la española y dejar la inglesa en borrador.
    """

    subpage_types = []
    parent_page_types = ["cms.NoteIndexPage"]

    # Default a hoy: una nota nueva nace con fecha, y el panel permite
    # adelantarla o atrasarla a mano (por ejemplo, para programar la nota).
    fecha = models.DateField("fecha de publicación", default=date.today)
    bajada = models.CharField(max_length=255, help_text="Una línea para el listado y el SEO.")
    cuerpo = RichTextField(features=["h2", "h3", "bold", "italic", "link", "ol", "ul", "image"])
    portada = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    content_panels = Page.content_panels + [
        FieldPanel("fecha"),
        FieldPanel("bajada"),
        FieldPanel("portada"),
        FieldPanel("cuerpo"),
    ]

    @property
    def portada_tarjeta(self):
        """La portada, para exponer su rendition de tarjeta en la API."""
        return self.portada

    @property
    def portada_cabecera(self):
        """La portada, para exponer su rendition de cabecera en la API."""
        return self.portada

    # Sin esto los campos existen en el modelo pero no viajan en la respuesta
    # de la API: `PagesAPIViewSet` sólo serializa lo que está acá declarado.
    #
    # `portada` a secas sólo trae id/meta/title del FK: no una URL usable. Las
    # dos renditions de abajo son la misma imagen ya redimensionada, con URL,
    # ancho y alto listos para pintar. Dos tamaños, no uno, porque el listado
    # y la nota tienen necesidades distintas:
    #   - `portada_tarjeta` (640x400, recortada): para la grilla del listado,
    #     donde todas las tarjetas necesitan la misma relación de aspecto
    #     (8:5) para no romper el layout, sin importar el aspecto original
    #     de cada portada.
    #   - `portada_cabecera` (ancho 1600, sin recortar): para la cabecera de
    #     la nota, donde la imagen es la pieza central del artículo y
    #     recortarla podría cortar lo importante de la composición; 1600
    #     alcanza para pantallas anchas sin mandar el original de golpe.
    api_fields = [
        APIField("fecha"),
        APIField("bajada"),
        APIField("cuerpo", serializer=RichTextAPIField()),
        APIField("portada"),
        APIField("portada_tarjeta", serializer=ImageRenditionField("fill-640x400")),
        APIField("portada_cabecera", serializer=ImageRenditionField("width-1600")),
    ]

    class Meta:
        verbose_name = "nota"
        verbose_name_plural = "notas"
