"""El formulario del admin para las notas: que cada traducción nazca vinculada.

La web declara el `hreflang` de una nota pidiendo sus traducciones por
`translation_key` (`web/lib/notes.ts`). Una nota en/pt creada con «Agregar
página» nace con una key nueva al azar y queda suelta: entre septiembre y
noviembre de 2026 pasó con ocho tandas sin que nada avisara. El botón
«Traducir» (`wagtail.contrib.simple_translation`) crea la copia vinculada, pero
el camino viejo seguía abierto; este formulario lo cierra.
"""

from django import forms
from django.utils.html import strip_tags
from wagtail.admin.forms import WagtailAdminPageForm
from wagtail.models import Locale


def _texto(html: str | None) -> str:
    """El texto del cuerpo, sin etiquetas ni atributos.

    Al pasar por Draftail el HTML vuelve con marcas propias (`data-block-key`),
    así que comparar el HTML crudo no detecta un cuerpo sin traducir.
    """
    return " ".join(strip_tags(html or "").split())


class NotaForm(WagtailAdminPageForm):
    def clean(self):
        cleaned_data = super().clean()
        nota = self.instance
        if nota.locale_id is None:
            # Página nueva: el locale lo pone Wagtail recién al guardar, a partir
            # del índice del que cuelga.
            nota.locale = self.parent_page.locale
        principal = Locale.get_default()
        if nota.locale_id == principal.id:
            return cleaned_data

        original = (
            type(nota)
            .objects.filter(translation_key=nota.translation_key, locale=principal)
            .first()
        )
        if original is None:
            raise forms.ValidationError(
                "Esta nota no está vinculada a una nota en español. Creala desde la "
                "nota en español con «Traducir», no con «Agregar página»: si no, la "
                "web no la declara como traducción y compite con la original."
            )
        # El borrador que crea «Traducir» es una copia de la española; se puede
        # guardar así, pero publicarlo pondría el texto en español bajo /en/ o /pt/.
        if self.data.get("action-publish") and _texto(cleaned_data.get("cuerpo")) == _texto(
            original.cuerpo
        ):
            self.add_error(
                "cuerpo",
                "El cuerpo es idéntico al de la nota en español: falta traducirlo.",
            )
        return cleaned_data
