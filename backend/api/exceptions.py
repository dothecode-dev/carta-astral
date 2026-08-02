"""Excepciones del dominio de créditos.

Viven acá (y no en interpretation_service) para que ledger e
interpretation_service las compartan sin import circular: interpretation_service
importa ledger (Task 14) y ledger necesita QuotaExceeded.
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


class QuotaExceeded(Exception):
    """La cuenta no tiene créditos disponibles para una generación nueva."""
