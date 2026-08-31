"""Excepciones del dominio de cobro.

Viven acá, y no en `interpretation_service`, para que cualquier módulo las
comparta sin import circular: `views` las atrapa e `interpretation_service` las
levanta. `SinDerecho` —la que dice que la cuenta no puede pagar lo que pidió—
no está acá sino en `api.canje`, junto a lo que la emite.
"""


from interpret.exceptions import InterpretationError


class CapReached(Exception):
    """Se alcanzó el tope global diario de generaciones nuevas."""


class GenerationInProgress(InterpretationError):
    """Otra petición ya está escribiendo esta misma lectura.

    No es un fallo: en unos segundos la lectura existe. Hereda de
    InterpretationError para que quien la capture en bloque siga andando, pero
    la API la responde aparte para que el cliente espere en vez de rendirse.
    """
