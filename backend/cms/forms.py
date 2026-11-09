"""El formulario del admin para las notas: que cada traducción nazca vinculada.

La web declara el `hreflang` de una nota pidiendo sus traducciones por
`translation_key` (`web/lib/notes.ts`). Que una nota en/pt esté
vinculada a la española lo exige el modelo (`NotePage.clean`), porque vale para
cualquier camino. Este formulario agrega lo que sólo se sabe en el admin: si se
está publicando. El borrador que crea «Traducir» es una copia de la española y
publicarlo así pondría texto en español bajo /en/ o /pt/.
"""

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
        principal = Locale.get_default()
        if nota.locale_id is None or nota.locale_id == principal.id:
            return cleaned_data
        # Que esté vinculada lo exige el modelo (`NotePage.clean`); acá sólo
        # falta lo que depende de saber si se está publicando.
        original = nota.get_translation_or_none(principal)
        if original is None:
            return cleaned_data
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
