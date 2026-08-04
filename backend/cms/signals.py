"""Le avisa a la web cuando una nota se publica o se despublica.

La web genera las notas como HTML estático en el build; sin este aviso, una
nota publicada no aparece hasta el siguiente deploy.
"""

import logging

import requests
from django.conf import settings
from django.dispatch import receiver
from wagtail.signals import page_published, page_unpublished

log = logging.getLogger(__name__)


def _avisar(page) -> None:
    url = getattr(settings, "REVALIDATE_URL", "")
    if not url:
        return
    try:
        requests.post(
            url,
            json={
                "secret": getattr(settings, "REVALIDATE_SECRET", ""),
                "slug": page.slug,
                "locale": page.locale.language_code,
            },
            timeout=5,
        )
    except OSError as e:
        # Que la web no conteste no puede impedir que la nota quede publicada:
        # el contenido ya está guardado y se verá en el próximo build.
        log.warning("no se pudo revalidar la web para %s: %s", page.slug, e)


@receiver(page_published)
def al_publicar(sender, instance, **kwargs):
    _avisar(instance)


@receiver(page_unpublished)
def al_despublicar(sender, instance, **kwargs):
    _avisar(instance)
