"""Las páginas del CMS. Sólo contenido: acá no entra nada de la aplicación."""

from datetime import date

from django.db import models
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Page


class NoteIndexPage(Page):
    """El listado de notas. Existe para colgar las notas de algún lado."""

    max_count = 1
    subpage_types = ["cms.NotePage"]

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

    class Meta:
        verbose_name = "nota"
        verbose_name_plural = "notas"
