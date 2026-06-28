class CoreError(Exception):
    """Base de errores del núcleo."""


class GeocodeTimezoneError(CoreError):
    """No se pudo resolver una timezone para las coordenadas dadas."""
