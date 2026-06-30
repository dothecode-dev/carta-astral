"""Excepciones del dominio de créditos.

Viven acá (y no en interpretation_service) para que ledger e
interpretation_service las compartan sin import circular: interpretation_service
importa ledger (Task 14) y ledger necesita QuotaExceeded.
"""


class CapReached(Exception):
    """Se alcanzó el tope global diario de generaciones nuevas."""


class QuotaExceeded(Exception):
    """La cuenta no tiene créditos disponibles para una generación nueva."""
