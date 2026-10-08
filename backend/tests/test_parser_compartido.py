"""El parser JSON por defecto es infraestructura compartida: vive en `config/`.

Lo cargan también las vistas DRF de `cms/` (API de Wagtail). Si viviera en
`api/`, `cms/` importaría `api/` en tiempo de ejecución a través de un string
de settings, que `lint-imports` no ve, y el contrato `cms/` <-> `api/` quedaría
roto sin que nada avise.
"""

from django.conf import settings


def test_el_parser_configurado_no_vive_en_api_ni_cms():
    for ruta in settings.REST_FRAMEWORK["DEFAULT_PARSER_CLASSES"]:
        assert not ruta.startswith(("api.", "cms.")), ruta
