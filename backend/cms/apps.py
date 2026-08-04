from django.apps import AppConfig


class CmsConfig(AppConfig):
    """El CMS de las notas.

    No importa `api` y `api` no lo importa: el contrato de import-linter lo
    verifica en CI. Acá no hay cuentas, cartas, interpretaciones ni créditos.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "cms"
