from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = 'api'

    def ready(self):
        from api import checks  # noqa: F401 — registra los checks de arranque
