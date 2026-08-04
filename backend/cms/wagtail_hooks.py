"""Handlers de rich text propios: la API es headless (RF3/RF4).

`config/urls.py` nunca incluye `wagtail.urls`: no hay ninguna vista que
sirva una `Page` directamente desde este backend. Los handlers de stock de
Wagtail para el rich text asumen que sí existe esa ruta:

- `PageLinkHandler` arma el `href` con `Page.get_url_parts()`, que sin
  `wagtail.urls` montado devuelve `(site_id, None, None)` (caso headless,
  documentado por el propio Wagtail) y el handler imprime el string
  "None" tal cual como href.
- El embed de imagen (`Format.image_to_html`) arma el `src` con
  `rendition.url`, que es relativo al backend. `portada_tarjeta` y
  `portada_cabecera` (`cms/models.py`) ya resuelven esto para las
  portadas usando `full_url`; al cuerpo le faltaba lo mismo.

Los dos handlers de acá abajo reemplazan a los de stock (mismo
`identifier`, así que pisan la registración de Wagtail: ver el hook al
final) para que `expand_db_html` —usado por `RichTextAPIField`,
`cms/models.py`— devuelva URLs absolutas y reales en los dos casos.
"""
from django.conf import settings
from django.forms.utils import flatatt
from django.utils.html import escape
from django.utils.safestring import mark_safe

from wagtail import hooks
from wagtail.images import get_image_model
from wagtail.images.formats import get_image_format
from wagtail.rich_text import EmbedHandler
from wagtail.rich_text.pages import PageLinkHandler

from cms.models import NoteIndexPage, NotePage


def _url_de_pagina(page) -> str:
    """La URL de una página del CMS tal como la sirve la web, no el backend.

    Esquema de rutas ya decidido para el plan del frontend: `/notas` y
    `/notas/<slug>` (docs/2026-07-31-spec-cms-wagtail.md). `page` llega ya
    resuelto a su tipo específico (`PageLinkHandler.get_many` usa
    `.specific()`).
    """
    base = settings.WEB_BASE_URL.rstrip("/")
    locale = page.locale.language_code
    if isinstance(page, NotePage):
        return f"{base}/{locale}/notas/{page.slug}"
    if isinstance(page, NoteIndexPage):
        return f"{base}/{locale}/notas"
    # Ningún otro tipo de página vive bajo este CMS hoy; un fallback a la
    # home del idioma es mejor que un href roto si algún día lo hay.
    return f"{base}/{locale}"


class NotaLinkHandler(PageLinkHandler):
    """`PageLinkHandler`, pero resolviendo la URL contra la web headless."""

    identifier = "page"

    @classmethod
    def expand_db_attributes_many(cls, attrs_list):
        pages = cls.get_many(attrs_list)
        return [
            f'<a href="{escape(_url_de_pagina(page))}">' if page else "<a>"
            for page in pages
        ]


class NotaImageEmbedHandler(EmbedHandler):
    """Embed de imagen, pero con `src` absoluto (igual que las portadas)."""

    identifier = "image"

    @staticmethod
    def get_model():
        return get_image_model()

    @classmethod
    def expand_db_attributes_many(cls, attrs_list):
        images = cls.get_many(attrs_list)
        tags = []
        for attrs, image in zip(attrs_list, images):
            if not image:
                tags.append('<img alt="">')
                continue
            image_format = get_image_format(attrs["format"])
            rendition = image.get_rendition(image_format.filter_spec)
            html_attrs = rendition.attrs_dict.copy()
            html_attrs["src"] = rendition.full_url
            html_attrs["alt"] = escape(attrs.get("alt", ""))
            if image_format.classname:
                html_attrs["class"] = image_format.classname
            tags.append(mark_safe(f"<img{flatatt(html_attrs)}>"))
        return tags

    @classmethod
    def extract_references(cls, attrs):
        yield cls.get_model(), attrs["id"], "", ""


@hooks.register("register_rich_text_features")
def _pisar_handlers_de_stock(features):
    # `cms` va después de `wagtail`/`wagtail.images` en INSTALLED_APPS, así
    # que este hook corre después y gana: `FeatureRegistry.register_*` es un
    # dict keyado por `identifier`, la última registración pisa a la
    # anterior (no hay merge ni chequeo de conflicto).
    features.register_link_type(NotaLinkHandler)
    features.register_embed_type(NotaImageEmbedHandler)
