"""Le avisa a la web cuando una nota se publica o se despublica.

La web genera las notas como HTML estático en el build; sin este aviso, una
nota publicada no aparece hasta el siguiente deploy.
"""

import logging

import requests
from django.conf import settings
from django.dispatch import receiver
from wagtail.signals import page_published, page_unpublished

from cms.models import NotePage

log = logging.getLogger(__name__)


def _avisar(page) -> None:
    url = settings.REVALIDATE_URL
    if not url:
        return
    try:
        respuesta = requests.post(
            url,
            json={
                "secret": settings.REVALIDATE_SECRET,
                "slug": page.slug,
                "locale": page.locale.language_code,
            },
            timeout=5,
        )
        if not respuesta.ok:
            # Un 4xx/5xx no lanza excepción: `requests.post` sólo levanta
            # `OSError` (red, timeout), nunca por el status code de la
            # respuesta. Sin este chequeo, un secreto mal configurado (401)
            # o una ruta que cambió (404) fallarían en silencio para
            # siempre. Nunca el secreto en el mensaje.
            log.warning(
                "la web respondió %s al revalidar %s", respuesta.status_code, page.slug
            )
    except OSError as e:
        # Que la web no conteste no puede impedir que la nota quede publicada:
        # el contenido ya está guardado y se verá en el próximo build.
        log.warning("no se pudo revalidar la web para %s: %s", page.slug, e)


# `sender=NotePage` y no a secas: sin acotarlo, publicar el índice —o
# cualquier tipo de página que se agregue más adelante— también le pega a la
# web, que revalida por slug y recibiría uno que no corresponde a ninguna nota.
@receiver(page_published, sender=NotePage)
def al_publicar(sender, instance, **kwargs):
    _avisar(instance)


@receiver(page_unpublished, sender=NotePage)
def al_despublicar(sender, instance, **kwargs):
    _avisar(instance)
