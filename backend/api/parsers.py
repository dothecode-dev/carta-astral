"""Parsers de DRF propios."""

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class JSONObjetoParser(JSONParser):
    """`JSONParser` que sólo acepta un objeto en la raíz.

    `[]`, `null`, `3` o `"x"` son JSON válido, así que el parser de DRF los
    deja pasar y la primera `request.data.get(...)` de la vista revienta con
    `AttributeError` (500). Ninguna ruta de la API espera otra cosa que un
    objeto; rechazarlo acá, una vez, da 400 en todas sin tocar cada vista.
    """

    def parse(self, stream, media_type=None, parser_context=None):
        datos = super().parse(stream, media_type, parser_context)
        if not isinstance(datos, dict):
            raise ParseError("el cuerpo tiene que ser un objeto JSON")
        return datos
