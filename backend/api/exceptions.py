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
    """Sin crédito del lote que compra el producto pedido.

    `lote` dice cuál faltó ("free" o "paid"): la web muestra "te quedaste
    sin lecturas gratis" o "comprá el informe completo" según el caso, que
    son dos pantallas distintas. El default "free" es sólo compatibilidad
    con quien instancie la excepción sin decir cuál lote faltó (no debería
    quedar ninguno tras esta tarea); `ledger.charge` siempre lo pasa
    explícito con el lote que realmente rechazó."""

    def __init__(self, lote: str = "free"):
        self.lote = lote
        super().__init__(f"sin créditos del lote {lote}")
